"""G7 (D-G7-06): offline replay of the REAL compiled hero graph against a
tracked bundle file -- no MCP network call, no LLM call, no Postgres
connection. This is the "replay bundle" plan section 14's G7 row asks
for, and the labelled demo fallback the project's Definition of Done
requires alongside the live proof ("a controlled live proof and an
explicitly labeled replay fallback both exist").

`build_recovery_graph` already takes every outermost I/O boundary as an
injected callable (`build.py:128-161`), so replay needs no cassette layer
inside `src/lantern/mcp/` and no change to the graph or the safety layer
-- it is a set of callables built from a file, plus a synthesised consent
that mirrors `apps/api/routes.py`'s `submit_consent` exactly (including
the deadline re-base, D39: omitting it makes the guard refuse on budget
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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

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
from src.lantern.memory.repository import IdempotencyState
from src.lantern.policies.loader import load_registry

IN_FLIGHT: IdempotencyState = "in_flight"

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
    write -- args-only keying cannot distinguish them."""

    fixture_id: str
    recorded_at: datetime
    versions: Mapping[str, str]
    inputs: Mapping[str, str]
    tool_schema_hashes: Mapping[str, Tuple[str, str, bool]]
    mcp: Mapping[str, List[Mapping[str, Any]]]
    llm: Mapping[str, List[Mapping[str, Any]]]
    expected_outcome: Mapping[str, Any]


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
    )


class BundlePlayer:
    """Serves recorded MCP/LLM responses from a bundle and stands in for
    Neon -- one object, so a caller cannot wire half the boundaries
    offline and half live. Mirrors `_FakeWriteBackend`
    (`tests/unit/test_write_path_interrupt_and_resume.py:110-140`)."""

    def __init__(self, bundle: ReplayBundle) -> None:
        self.bundle = bundle
        self._cursors: Dict[str, int] = {}
        self._planner_cursor = 0
        self._explainer_cursor = 0
        self.consents: Dict[str, ConsentRecord] = {}
        self.journal: Dict[Tuple[str, str, str], IdempotencyState] = {}
        self.receipts: List[Receipt] = []

    def call(self, tool_name: str, args: Mapping[str, Any]) -> Dict[str, Any]:
        key = response_key(tool_name, args)
        queue = self.bundle.mcp.get(key)
        if queue is None:
            raise ReplayMismatch(
                f"no recorded response for {key} "
                f"(tool={tool_name!r}, args={dict(args)!r})"
            )
        cursor = self._cursors.get(key, 0)
        if cursor >= len(queue):
            raise ReplayMismatch(f"{key} exhausted after {cursor} recorded call(s)")
        self._cursors[key] = cursor + 1
        return dict(queue[cursor])

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
        including the deadline re-base (D39) -- omitting it makes the
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


def replay(bundle: ReplayBundle) -> ReplayResult:
    """Builds the REAL graph via `build_recovery_graph`, every boundary
    bound to `player`, an `InMemorySaver`, and the bundle's own recorded
    clock; runs to the interrupt, records consent, resumes, and returns
    the final state and every receipt saved (D42's second consent round
    can produce more than one)."""
    player = BundlePlayer(bundle)

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
        planner_call=player.next_planner,
        explainer_call=player.next_explainer,
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

    config: RunnableConfig = {
        "configurable": {"thread_id": f"replay-{bundle.fixture_id}"}
    }
    initial_state = new_recovery_state(
        session_id=bundle.inputs["session_id"],
        trace_id=bundle.inputs["trace_id"],
        now=bundle.recorded_at,
        owner=bundle.inputs["owner"],
    )
    paused_state = graph.invoke(initial_state, config)
    consented_action_id = ""

    # D42: a verified write that leaves the blocker standing returns the
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
    )
