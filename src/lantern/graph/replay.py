"""offline replay of the REAL compiled hero graph against a
tracked bundle file -- no MCP network call, no LLM call, no Postgres
connection. This is the "replay bundle" plan section 14's replay row asks
for, and the labelled demo fallback the project's Definition of Done
requires alongside the live proof ("a controlled live proof and an
explicitly labeled replay fallback both exist").

`build_recovery_graph` already takes every outermost I/O boundary as an
injected callable (`build.py:128-161`), so replay needs no cassette layer
inside `src/lantern/mcp/` and no change to the graph or the safety layer
-- it is a set of callables built from a file, plus a synthesised consent
that mirrors `apps/api/routes.py`'s `submit_consent` exactly (including
the deadline re-base: omitting it makes the guard refuse on budget
reserve).

`BundlePlayer`'s four Postgres stand-ins and its MCP/LLM queues are the
same shape as `_FakeWriteBackend`
(`tests/unit/test_write_path_interrupt_and_resume.py:110-140`) -- promoted
here so both share one implementation instead of two copies drifting
apart.

An `action_id` is a fresh `uuid4` every run
(`domain/action_proposal_builder.py:90`), so a replayed `Receipt` can
never equal a recorded one byte-for-byte. `expected_outcome` in the
bundle therefore excludes `action_id`/`created_at`/`trace_id`; the caller
asserts those separately (that the receipt's `action_id` equals the
consented proposal's own id -- the actual binding property the field
exists to prove).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from src.lantern.domain.consent_hash import (
    canonical_json,
    compute_args_hash,
    compute_state_hash,
)
from src.lantern.domain.models import ActionProposal, ConsentRecord, Receipt
from src.lantern.graph.build import build_recovery_graph
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.graph.state import ACTIVE_EXECUTION_SECONDS, new_recovery_state
from src.lantern.mcp.errors import McpAdapterError
from src.lantern.memory.repository import IdempotencyState
from src.lantern.policies.loader import load_registry

IN_FLIGHT: IdempotencyState = "in_flight"

# mirrors `scripts/record_replay_bundle.TAPED_ERROR_KEY`.
# Not imported from there -- `scripts/` is not a package this layer
# may depend on; the recorder's own test pins the two agree.
TAPED_ERROR_KEY = "__mcp_error__"

# plan section 11.1 -- mirrors `apps/api/routes.py`'s own `CONSENT_TTL`.
# Not imported from there: `apps/api` is the interface layer and this
# module is `application` (graph/**) -- importing "up" would invert the
# direction `tests/unit/test_layering.py` enforces for every other
# boundary in this project.
_CONSENT_TTL = timedelta(minutes=5)


class ReplayMismatch(RuntimeError):
    """Raised instead of returning `{}` when the bundle has no recorded
    response for a call the graph actually made -- an exhausted queue or
    an unknown key. This is how a bundle detects graph drift: a node
    added, removed, or reordered changes the call sequence, and replay
    fails loudly naming the key it wanted, rather than silently feeding
    the graph an empty payload."""


def response_key(tool_name: str, args: Mapping[str, Any]) -> str:
    """`f"{tool_name}:{sha256(canonical_json(args))[:12]}"`. Reuses
    `domain.consent_hash.canonical_json` -- the project's one stable
    canonicalizer -- so there is no second one to drift from it."""
    digest = hashlib.sha256(canonical_json(args).encode("utf-8")).hexdigest()[:12]
    return f"{tool_name}:{digest}"


@dataclass(frozen=True)
class ReplayBundle:
    """The parsed contents of one bundle file. `mcp`/`llm` values are
    ORDERED QUEUES, not single responses: the hero flow calls
    `fetch_cart_by_id` with identical args three times (read, the guard's
    re-read, the read-back) and the third must return the cart AFTER the
    write -- args-only keying cannot distinguish them.

    `mcp_by_tool` is a SECOND, tool-name-only queue,
    consulted only when `mcp`'s args-keyed lookup misses -- built by
    `record_replay_bundle.py` from the SAME tape, grouped by tool name in
    call order, never hand-written. It exists because the 18 core repeats
    run the real live planner against replayed MCP, and
    `silpo_find_products_batch`'s args carry that planner's own search
    terms -- which vary run to run and never match the exact-args hash
    recorded at tape time. Optional for backward compatibility with
    bundles recorded."""

    fixture_id: str
    recorded_at: datetime
    versions: Mapping[str, str]
    inputs: Mapping[str, str]
    tool_schema_hashes: Mapping[str, Tuple[str, str, bool]]
    mcp: Mapping[str, List[Mapping[str, Any]]]
    llm: Mapping[str, List[Mapping[str, Any]]]
    expected_outcome: Mapping[str, Any]
    mcp_by_tool: Mapping[str, List[Mapping[str, Any]]] = field(default_factory=dict)


def load_bundle(path: Path) -> ReplayBundle:
    envelope = json.loads(path.read_text(encoding="utf-8"))
    payload = envelope["payload"]
    return ReplayBundle(
        fixture_id=envelope["fixture_id"],
        recorded_at=datetime.fromisoformat(payload["recorded_at"]),
        versions=payload["versions"],
        inputs=payload["inputs"],
        tool_schema_hashes={
            name: (value[0], value[1], value[2])
            for name, value in payload["tool_schema_hashes"].items()
        },
        mcp=payload["mcp"],
        llm=payload["llm"],
        expected_outcome=envelope["expected_outcome"],
        # absent on bundles recorded -- `.get`
        # with a `{}` default keeps those bundles loadable unchanged.
        mcp_by_tool=payload.get("mcp_by_tool", {}),
    )


class BundlePlayer:
    """Serves recorded MCP/LLM responses from a bundle and stands in for
    Neon -- one object, so a caller cannot wire half the boundaries
    offline and half live. Mirrors `_FakeWriteBackend`
    (`tests/unit/test_write_path_interrupt_and_resume.py:110-140`)."""

    def __init__(self, bundle: ReplayBundle) -> None:
        self.bundle = bundle
        self._cursors: Dict[str, int] = {}
        self._by_tool_cursors: Dict[str, int] = {}
        self._planner_cursor = 0
        self._explainer_cursor = 0
        # every call this player served, in order. The metrics
        # need the args the graph ACTUALLY wrote, to hash independently
        # against the consent's own `args_hash` -- taking the guard's word
        # for that would make ConsentBindingIntegrity a tautology.
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self.consents: Dict[str, ConsentRecord] = {}
        self.journal: Dict[Tuple[str, str, str], IdempotencyState] = {}
        self.receipts: List[Receipt] = []

    def call(self, tool_name: str, args: Mapping[str, Any]) -> Dict[str, Any]:
        self.calls.append((tool_name, dict(args)))
        key = response_key(tool_name, args)
        # the fallback queue is the tape's calls to this tool IN
        # ORDER, so its position must count EVERY call to the tool, not
        # only the ones it served. `find_products_batch` is called twice
        # per round -- once from the cart's own names (an args hit) and
        # once from the live planner's terms (a miss) -- and a cursor that
        # only moved on misses answered the planner's search with the
        # availability response recorded for `compare_channels`.
        by_tool_cursor = self._by_tool_cursors.get(tool_name, 0)
        self._by_tool_cursors[tool_name] = by_tool_cursor + 1

        queue = self.bundle.mcp.get(key)
        if queue is not None:
            cursor = self._cursors.get(key, 0)
            if cursor < len(queue):
                self._cursors[key] = cursor + 1
                return self._serve(queue[cursor])
            raise ReplayMismatch(f"{key} exhausted after {cursor} recorded call(s)")

        # the args-keyed lookup missed. Fall back to the
        # tool-name-only queue, consulted ONLY here -- an exact args match
        # always wins because it is strictly more specific, and a tool
        # with no fallback queue at all raises exactly as before.
        fallback_queue = self.bundle.mcp_by_tool.get(tool_name)
        if fallback_queue is not None:
            if by_tool_cursor < len(fallback_queue):
                return self._serve(fallback_queue[by_tool_cursor])
            raise ReplayMismatch(
                f"{tool_name} fallback queue exhausted after "
                f"{by_tool_cursor} recorded call(s)"
            )

        raise ReplayMismatch(
            f"no recorded response for {key} "
            f"(tool={tool_name!r}, args={dict(args)!r})"
        )

    @staticmethod
    def _serve(entry: Mapping[str, Any]) -> Dict[str, Any]:
        """A taped REFUSAL is replayed as a refusal. Live, the
        server rejects `get_time_slots` for the two channels that resolve
        no real branch, and `compare_channels_node` degrades those
        channels rather than aborting -- a bundle that served them an
        empty success would replay a different graph run than the one it
        recorded."""
        if TAPED_ERROR_KEY in entry:
            raise McpAdapterError(str(entry[TAPED_ERROR_KEY]))
        return dict(entry)

    def next_planner(self, state: Any) -> SearchIntent:
        del state  # the recorded output does not depend on re-deriving it
        queue = self.bundle.llm["planner"]
        if self._planner_cursor >= len(queue):
            raise ReplayMismatch("planner response queue exhausted")
        raw = queue[self._planner_cursor]
        self._planner_cursor += 1
        return SearchIntent(**raw)

    def next_explainer(self, proposal: ActionProposal) -> ExplainerOutput:
        queue = self.bundle.llm["explainer"]
        if self._explainer_cursor >= len(queue):
            raise ReplayMismatch("explainer response queue exhausted")
        raw = queue[self._explainer_cursor]
        self._explainer_cursor += 1
        # The recorded `action_id` cannot match a fresh uuid4 -- bind the
        # explainer's own output to whichever proposal it is narrating,
        # same as a real live call would (the explainer only ever
        # receives one already-decided candidate at a time).
        return ExplainerOutput(**{**raw, "action_id": proposal.action_id})

    # -- Postgres stand-ins (same shape as `_FakeWriteBackend`) --

    def load_consent(self, action_id: str) -> Tuple[Optional[ConsentRecord], bool]:
        record = self.consents.get(action_id)
        if record is None:
            return None, True
        return record, False

    def claim_and_consume(
        self, owner: str, cart_id: str, action_id: str, args_hash: str
    ) -> Tuple[bool, IdempotencyState]:
        del args_hash
        key = (owner, cart_id, action_id)
        if key in self.journal:
            return False, self.journal[key]
        consent = self.consents[action_id]
        self.consents[action_id] = consent.model_copy(
            update={"consumed_at": datetime.now(timezone.utc)}
        )
        self.journal[key] = IN_FLIGHT
        return True, IN_FLIGHT

    def mark_action(
        self, owner: str, cart_id: str, action_id: str, state: IdempotencyState
    ) -> None:
        self.journal[(owner, cart_id, action_id)] = state

    def save_receipt(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)

    def tool_schema_hashes(self, tool_name: str) -> Tuple[str, str, bool]:
        return self.bundle.tool_schema_hashes.get(
            tool_name, ("reviewed-hash", "reviewed-hash", False)
        )

    def grant_and_bind_consent(
        self, graph: Any, config: RunnableConfig, proposal: ActionProposal, cart: Any
    ) -> None:
        """Mirrors `apps/api/routes.py`'s `submit_consent` exactly,
        including the deadline re-base -- omitting it makes the
        guard refuse on insufficient budget reserve, the way a live run
        did before that fix landed."""
        now = self.bundle.recorded_at
        consent = ConsentRecord(
            action_id=proposal.action_id,
            session_id=self.bundle.inputs["session_id"],
            owner=self.bundle.inputs["owner"],
            cart_id=cart.cart_id,
            canonical_args=proposal.canonical_args,
            args_hash=compute_args_hash(proposal.canonical_args),
            state_hash=compute_state_hash(cart),
            created_at=now,
            expires_at=now + _CONSENT_TTL,
        )
        self.consents[proposal.action_id] = consent
        graph.update_state(
            config,
            {
                "consent_action_id": proposal.action_id,
                "deadline": now + timedelta(seconds=ACTIVE_EXECUTION_SECONDS),
            },
        )


@dataclass(frozen=True)
class ReplayResult:
    final_state: Mapping[str, Any]
    receipts: List[Receipt]
    consented_action_id: str
    # the player itself, so a caller can read the journal, the
    # consents and the served calls -- the three things the metrics need
    # and none of which survive in `final_state`.
    player: Optional["BundlePlayer"] = None


def replay(
    bundle: ReplayBundle,
    *,
    planner_call: Optional[Callable[[Any], SearchIntent]] = None,
    explainer_call: Optional[Callable[[ActionProposal], ExplainerOutput]] = None,
    thread_id: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
) -> ReplayResult:
    """Builds the REAL graph via `build_recovery_graph`, every boundary
    bound to `player`, an `InMemorySaver`, and the bundle's own recorded
    clock; runs to the interrupt, records consent, resumes, and returns
    the final state and every receipt saved (the second consent round
    can produce more than one).

    `planner_call`/`explainer_call`: omitted (the
    default), MCP AND the planner/explainer both replay from the bundle's
    tape -- today's fully-offline behavior, unchanged. Passed, they let
    the 18 core repeats wire in the REAL live planner/explainer
    while MCP still replays from the tape (via `mcp_by_tool`'s fallback
    for the planner's own varying search terms) -- "live LLM against
    replayed MCP", the configuration the author approved at the kickoff
    kickoff."""
    player = BundlePlayer(bundle)
    planner_call = planner_call or player.next_planner
    explainer_call = explainer_call or player.next_explainer

    def now() -> datetime:
        return bundle.recorded_at

    def fetch_my_cart() -> Dict[str, Any]:
        return player.call("silpo_get_my_shopping_cart", {})

    def fetch_cart_by_id(cart_id: str) -> Dict[str, Any]:
        return player.call("silpo_get_shopping_cart_by_id", {"cart_id": cart_id})

    def fetch_delivery_types(latitude: float, longitude: float) -> Dict[str, Any]:
        return player.call(
            "silpo_get_available_delivery_types",
            {"latitude": latitude, "longitude": longitude},
        )

    def fetch_time_slots(branch_id: str, delivery_types: Any) -> Dict[str, Any]:
        return player.call(
            "silpo_get_time_slots",
            {"branch_id": branch_id, "delivery_types": list(delivery_types)},
        )

    def fetch_find_products_batch(
        branch_id: str, delivery_type: str, start: str, end: str, names: Any
    ) -> Dict[str, Any]:
        return player.call(
            "silpo_find_products_batch",
            {
                "branch_id": branch_id,
                "delivery_type": delivery_type,
                "start": start,
                "end": end,
                "names": list(names),
            },
        )

    def call_write_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return player.call(tool_name, args)

    checkpointer = InMemorySaver()
    graph = build_recovery_graph(
        fetch_my_cart=fetch_my_cart,
        fetch_cart_by_id=fetch_cart_by_id,
        registry=load_registry(),
        fetch_delivery_types=fetch_delivery_types,
        fetch_time_slots=fetch_time_slots,
        fetch_find_products_batch=fetch_find_products_batch,
        planner_call=planner_call,
        explainer_call=explainer_call,
        now=now,
        checkpointer=checkpointer,
        tools_schema_hash=bundle.versions.get("schema_hash", ""),
        load_consent=player.load_consent,
        call_write_tool=call_write_tool,
        claim_and_consume=player.claim_and_consume,
        mark_action=player.mark_action,
        save_receipt=player.save_receipt,
        tool_schema_hashes=player.tool_schema_hashes,
    )

    # the caller may name the thread. The 18 core repeats run
    # the same bundle three times, and a thread id derived from the
    # fixture alone gives all three the same handle -- so a result row
    # could not be matched to the trace it came from, which is the one
    # thing section 13.4's per-run `trace` field exists for.
    # `tags` reach the ROOT run. `traced_llm_call` tags only the spans it
    # wraps, so a project list filtered by tag showed no runs at all even
    # though every planner/explainer span carried them (found on the second round).
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id or f"replay-{bundle.fixture_id}"},
        "tags": list(tags) if tags else [],
    }
    initial_state = new_recovery_state(
        session_id=bundle.inputs["session_id"],
        trace_id=bundle.inputs["trace_id"],
        now=bundle.recorded_at,
        owner=bundle.inputs["owner"],
    )
    paused_state = graph.invoke(initial_state, config)
    consented_action_id = ""

    # a verified write that leaves the blocker standing returns the
    # graph to `diagnose` and parks on the interrupt again -- bounded by
    # `MAX_WRITE_ROUNDS`. Every round the bundle has a matching candidate
    # for is replayed; a round the bundle cannot satisfy stops the loop
    # rather than raising, so a bundle recorded for N rounds replays
    # exactly N rounds.
    state = paused_state
    while state.get("status") == "awaiting_consent" and state.get("candidates"):
        candidates = state["candidates"]
        proposal = candidates[0]
        cart = state["cart"]
        player.grant_and_bind_consent(graph, config, proposal, cart)
        consented_action_id = proposal.action_id
        state = graph.invoke(None, config)
        if state.get("status") not in ("diagnosed", "awaiting_consent"):
            break

    return ReplayResult(
        final_state=state,
        receipts=list(player.receipts),
        consented_action_id=consented_action_id,
        player=player,
    )
