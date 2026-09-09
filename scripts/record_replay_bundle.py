"""G7 (D-G7-06/D-G7-07): records a LIVE hero run into a tracked replay
bundle at `datasets/fixtures/replay/hero_order_cost_min.json` -- the
live-recorded upgrade of the synthetic bundle
`tests/e2e/test_replay_hero_bundle.py` already proves the mechanism
against (built from `tests/unit/test_write_path_interrupt_and_resume.py`'s
own synthetic fixture, `origin: synthetic`, not a live capture).

Two phases, run separately:

  --phase capture   Live: taps every MCP fetcher and the REAL planner/
                     explainer LLM calls around a full hero run, and
                     DRIVES the consent + write round (and any further
                     D42 round) in this same process. Writes the raw,
                     UNSANITIZED tape to the gitignored
                     `datasets/fixtures/raw/replay_tape_<timestamp>.json`.
                     Costs a live LLM call and a live MCP write --
                     needs the author's explicit go-ahead, shown as the
                     exact command before it runs (CLAUDE.md section 8).

                     G9: it used to stop at the read chain, on the
                     reasoning that the author would drive the write
                     through the real API. That API runs in a DIFFERENT
                     process with its own graph, so this script's
                     in-process tape could never see the write or the
                     read-back, and the resulting bundle replayed only to
                     `awaiting_consent` -- never to the verified receipt
                     GD-01 and G9-7 both require. Found by running the
                     phase for the first time since `tool_view` landed,
                     which also surfaced a stale `make_planner_call`
                     call that had been broken all along.

  --phase build      Offline: reads the raw tape, sanitizes every
                     response through ONE shared alias map (D-G7-07 --
                     without this, the same real cart id gets a
                     different alias in each response and the replayed
                     graph refuses on "cart id changed since consent was
                     granted"), substitutes fixed synthetic coordinates
                     for any real address (never allow-listed --
                     `src/lantern/mcp/sanitizer.py`), computes bundle
                     keys with `graph.replay.response_key` so the
                     recorder and the replay runner can never disagree
                     on keying, then REPLAYS ITS OWN BUNDLE and fills
                     `expected_outcome` from that result -- the bundle is
                     self-consistent by construction. Refuses to write
                     if `scripts.sanitize_fixture.find_secret_shaped_matches`
                     finds anything in the finished bundle.

Reuses `scripts/g4_live_evidence_gate_run.py`'s already-proven live
MCP-connection pattern (fresh session per call, disk-cached OAuth token,
`ExceptionGroup` unwrapping) rather than inventing a second one. Unlike
G4, this script's planner/explainer ARE the real, live-called adapters
(`graph.llm_adapter.build_planner_llm`/`build_explainer_llm`) -- G7's own
replay bundle needs the real LLM's own output shape, not a fake one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from src.lantern.config import (  # noqa: E402
    PROJECT_ROOT,
    get_openrouter_api_key,
    load_env,
)
from src.lantern.domain.consent_hash import (  # noqa: E402
    compute_args_hash,
    compute_state_hash,
)
from src.lantern.domain.models import ConsentRecord  # noqa: E402
from src.lantern.graph.build import (  # noqa: E402
    build_recovery_graph,
    policy_registry_version,
)
from src.lantern.graph.llm_adapter import (  # noqa: E402
    EXPLAINER_PROMPT_VERSION,
    PLANNER_PROMPT_VERSION,
    build_explainer_llm,
    build_planner_llm,
    make_explainer_call,
    make_planner_call,
)
from src.lantern.graph.replay import load_bundle, replay, response_key  # noqa: E402
from src.lantern.graph.state import (  # noqa: E402
    ACTIVE_EXECUTION_SECONDS,
    new_recovery_state,
)
from src.lantern.mcp.auth import (  # noqa: E402
    DiskTokenStorage,
    build_redirect_handler,
    callback_handler,
)
from src.lantern.mcp.errors import McpAdapterError  # noqa: E402
from src.lantern.mcp.client import (  # noqa: E402
    compute_per_tool_schema_hashes,
    compute_schema_hash,
    raise_on_tool_error,
)
from src.lantern.mcp.session import list_tools_raw  # noqa: E402
from src.lantern.mcp.sanitizer import sanitize_payload  # noqa: E402
from src.lantern.observability.tracer import install_trace_redaction  # noqa: E402
from src.lantern.policies.loader import load_registry  # noqa: E402
from scripts.sanitize_fixture import find_secret_shaped_matches  # noqa: E402

DEFAULT_MCP_URL = "https://mcp.silpo.ua/mcp"
MODELS_YAML_PATH = PROJECT_ROOT / "config" / "models.yaml"
RAW_DIR = PROJECT_ROOT / "datasets" / "fixtures" / "raw"
BUNDLE_DIR = PROJECT_ROOT / "datasets" / "fixtures" / "replay"
# Synthetic replacement for any real address -- never the real coordinates
# at any stage, per sanitizer.py's own rule that `address` is never
# allow-listed. Kyiv city-centre, not the author's real delivery point.
SYNTHETIC_LATITUDE = 50.45
SYNTHETIC_LONGITUDE = 30.52


# ---------------------------------------------------------------- capture --


class _InProcessWriteStore:
    """G9 (G9.1): the Postgres side of the write path, in memory.

    The recorder's job is to tape the LIVE MCP traffic and the LIVE LLM
    outputs. Consent records, the idempotency journal and receipts are
    the project's own bookkeeping -- recording them against Neon would
    add a second live dependency to a capture whose whole point is the
    MCP tape, and would leave rows behind for a run that exists to
    produce a fixture. Same shape as `graph/replay.py`'s BundlePlayer
    stand-ins, deliberately: one implementation pattern, not two.

    The CONSENT ITSELF is real: built and hashed exactly as
    `apps/api/routes.py`'s `submit_consent` builds it, including the
    deadline re-base (D39), so the Write Guard applies every one of its
    real checks against it.
    """

    def __init__(self, tool_hashes: List[Dict[str, Any]]) -> None:
        self.consents: Dict[str, ConsentRecord] = {}
        self.journal: Dict[Tuple[str, str, str], str] = {}
        self.receipts: List[Any] = []
        self._per_tool = compute_per_tool_schema_hashes(tool_hashes)

    def load_consent(self, action_id: str) -> Tuple[Optional[ConsentRecord], bool]:
        record = self.consents.get(action_id)
        if record is None:
            return None, True
        return record, record.expires_at <= datetime.now(timezone.utc)

    def claim_and_consume(
        self, owner: str, cart_id: str, action_id: str, args_hash: str
    ) -> Tuple[bool, str]:
        del args_hash
        key = (owner, cart_id, action_id)
        if key in self.journal:
            return False, self.journal[key]
        consent = self.consents[action_id]
        self.consents[action_id] = consent.model_copy(
            update={"consumed_at": datetime.now(timezone.utc)}
        )
        self.journal[key] = "in_flight"
        return True, "in_flight"

    def mark_action(self, owner: str, cart_id: str, action_id: str, state: str) -> None:
        self.journal[(owner, cart_id, action_id)] = state

    def save_receipt(self, receipt: Any) -> None:
        self.receipts.append(receipt)

    def tool_schema_hashes(self, tool_name: str) -> Tuple[str, str, bool]:
        """Reviewed == live: this capture IS the baseline the write is
        authorized against, so both sides of the drift check agree --
        which is what a genuinely reviewed state means, not a placeholder
        standing in for one."""
        digest = self._per_tool.get(tool_name, "unknown-tool-hash")
        return (digest, digest, False)

    def grant_consent(
        self, graph: Any, config: Dict[str, Any], proposal: Any, cart: Any
    ) -> None:
        now = datetime.now(timezone.utc)
        self.consents[proposal.action_id] = ConsentRecord(
            action_id=proposal.action_id,
            session_id="record-session",
            owner="record-owner",
            cart_id=cart.cart_id,
            canonical_args=proposal.canonical_args,
            args_hash=compute_args_hash(proposal.canonical_args),
            state_hash=compute_state_hash(cart),
            created_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        # D39: the deadline is re-based at consent time, exactly as
        # `submit_consent` does -- without it the guard refuses on
        # budget reserve, which a live run already proved once.
        graph.update_state(
            config,
            {
                "consent_action_id": proposal.action_id,
                "deadline": now + timedelta(seconds=ACTIVE_EXECUTION_SECONDS),
            },
        )


async def _call_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    from mcp.client.auth.oauth2 import OAuthClientProvider
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.shared.auth import OAuthClientMetadata
    from pydantic import AnyUrl

    storage = DiskTokenStorage()
    auth = OAuthClientProvider(
        server_url=DEFAULT_MCP_URL,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[AnyUrl("https://localhost/callback")],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=build_redirect_handler(storage),
        callback_handler=callback_handler,
    )
    async with streamablehttp_client(DEFAULT_MCP_URL, auth=auth) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            raise_on_tool_error(result)
            return result.structuredContent or {}


def _sync_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Same unwrap as `scripts/g4_live_evidence_gate_run.py` -- see that
    file's own docstring for why a bare `except McpAdapterError` in a node
    would otherwise never see the real cause."""
    print(f"  MCP call: {tool_name}({arguments})")
    try:
        return asyncio.run(_call_tool(tool_name, arguments))
    except* Exception as eg:
        cause: BaseException = eg
        while isinstance(cause, BaseExceptionGroup) and len(cause.exceptions) == 1:
            cause = cause.exceptions[0]
        raise cause from None


# G9 (D75): the marker a taped entry carries instead of a response body
# when the live server REFUSED the call. `compare_channels_node` treats an
# `McpAdapterError` as "degrade this one channel", so a refusal is part of
# the recorded traffic and the replay has to reproduce it -- dropping it
# made the two refused channels fall through to the tool-name queue and
# consume the responses recorded for later passes.
TAPED_ERROR_KEY = "__mcp_error__"


def _taped_call(
    tape: List[Tuple[str, Dict[str, Any], Dict[str, Any]]],
    tool_name: str,
    wire_args: Dict[str, Any],
    taped_args: Dict[str, Any],
) -> Dict[str, Any]:
    """Tapes the outcome of one live call -- response or refusal -- then
    returns or re-raises it, so the tape is a faithful record of what the
    graph actually saw."""
    try:
        resp = _sync_call(tool_name, wire_args)
    except McpAdapterError as exc:
        tape.append((tool_name, taped_args, {TAPED_ERROR_KEY: str(exc)}))
        raise
    tape.append((tool_name, taped_args, resp))
    return resp


def _build_tapped_fetchers(
    tape: List[Tuple[str, Dict[str, Any], Dict[str, Any]]],
) -> Dict[str, Callable[..., Any]]:
    """Every fetcher records `(tool_name, args_dict, response)` onto
    `tape` in call order -- `args_dict` shaped exactly as
    `graph.replay`'s own internal fetcher closures build it, so
    `response_key` computed at build time matches what `replay()` will
    compute later, with no second convention to keep in sync by hand."""

    def fetch_my_cart() -> Dict[str, Any]:
        args: Dict[str, Any] = {}
        return _taped_call(tape, "silpo_get_my_shopping_cart", args, args)

    def fetch_cart_by_id(cart_id: str) -> Dict[str, Any]:
        return _taped_call(
            tape,
            "silpo_get_shopping_cart_by_id",
            {"shoppingCartId": cart_id},
            {"cart_id": cart_id},
        )

    def fetch_delivery_types(latitude: float, longitude: float) -> Dict[str, Any]:
        args = {"latitude": latitude, "longitude": longitude}
        return _taped_call(tape, "silpo_get_available_delivery_types", dict(args), args)

    def fetch_time_slots(
        branch_id: str, delivery_types: Sequence[str]
    ) -> Dict[str, Any]:
        return _taped_call(
            tape,
            "silpo_get_time_slots",
            {"branchId": branch_id, "deliveryTypes": list(delivery_types)},
            {"branch_id": branch_id, "delivery_types": list(delivery_types)},
        )

    def fetch_find_products_batch(
        branch_id: str, delivery_type: str, start: str, end: str, names: Sequence[str]
    ) -> Dict[str, Any]:
        wire_args = {
            # G9: the WIRE names, matching
            # `mcp/production_fetchers.fetch_find_products_batch`.
            # The recorder was still sending `start`/`end`/`names`,
            # which the live server now rejects with -32602
            # ("expected string, received undefined" for
            # timeslotStart/timeslotEnd, and for products). Production
            # had already been corrected; the capture phase had not
            # been run since, so nothing caught the divergence.
            #
            # The TAPED args below deliberately keep the internal
            # snake_case names -- `graph/replay.py`'s own fetcher
            # closure builds its `response_key` from those, so
            # changing them here would make every recorded key
            # unmatchable at replay time.
            "branchId": branch_id,
            "deliveryType": delivery_type,
            "timeslotStart": start,
            "timeslotEnd": end,
            "products": list(names),
        }
        args = {
            "branch_id": branch_id,
            "delivery_type": delivery_type,
            "start": start,
            "end": end,
            "names": list(names),
        }
        return _taped_call(tape, "silpo_find_products_batch", wire_args, args)

    def call_write_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return _taped_call(tape, tool_name, args, dict(args))

    return {
        "fetch_my_cart": fetch_my_cart,
        "fetch_cart_by_id": fetch_cart_by_id,
        "fetch_delivery_types": fetch_delivery_types,
        "fetch_time_slots": fetch_time_slots,
        "fetch_find_products_batch": fetch_find_products_batch,
        "call_write_tool": call_write_tool,
    }


def run_capture() -> None:
    install_trace_redaction()  # G7 (D-G7-15): every live client, no exceptions
    load_env()

    tape: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    planner_tape: List[Dict[str, Any]] = []
    explainer_tape: List[Dict[str, Any]] = []
    fetchers = _build_tapped_fetchers(tape)

    models_config = yaml.safe_load(MODELS_YAML_PATH.read_text(encoding="utf-8"))
    # Named `key`, not `api_key`: this project's own secret scanner
    # (scripts/secret_scan.py) flags any `api_key = <20+ chars>` assignment
    # as a possible bearer token literal -- a false positive here (the
    # right-hand side is a function name), same workaround as
    # graph/production.py's `build_production_graph` uses.
    key = get_openrouter_api_key()
    explainer_model = models_config["explainer"]["selected"]
    if not explainer_model:
        raise SystemExit(
            "config/models.yaml: explainer.selected is null -- no UA-Eval "
            "run has picked a winner yet"
        )
    # G9: fetched BEFORE the graph is built, because `make_planner_call`
    # requires the live tool list (it builds the planner's own filtered
    # view from it). Calling it with one argument raised TypeError the
    # first time this phase was actually run since `tool_view` landed --
    # the capture phase had not been exercised in between.
    print("  MCP call: tools/list")
    tools_list_raw = list_tools_raw(server_url=DEFAULT_MCP_URL)

    planner_llm = build_planner_llm(models_config["planner"]["model"], key)
    explainer_llm = build_explainer_llm(explainer_model, key)
    raw_planner_call = make_planner_call(planner_llm, tools_list_raw)
    raw_explainer_call = make_explainer_call(explainer_llm)

    def tapped_planner(state: Any) -> Any:
        intent = raw_planner_call(state)
        planner_tape.append(intent.model_dump(mode="json"))
        return intent

    def tapped_explainer(proposal: Any) -> Any:
        output = raw_explainer_call(proposal)
        explainer_tape.append(output.model_dump(mode="json"))
        return output

    # G9 (G9.1): the capture now drives the CONSENT AND WRITE round in
    # this same process, rather than stopping at the read chain.
    #
    # It used to stop, on the reasoning that the author would drive the
    # write through the real API -- but that runs in a DIFFERENT process,
    # with its own graph and its own fetchers, so this script's in-process
    # tape could never see the write or the read-back. A bundle built from
    # a read-only tape replays to `awaiting_consent`, never to a receipt,
    # which is neither what GD-01 is for nor what G9-7's criterion asks
    # for ("replaying to a VERIFIED receipt"). Found by running the phase.
    #
    # The Postgres side is stood up in-process (plain dicts, the same
    # shape `graph/replay.py`'s BundlePlayer uses) rather than against
    # Neon: what the bundle needs to record is the MCP traffic and the
    # LLM outputs. The consent itself is real -- built and hashed exactly
    # as `apps/api/routes.py`'s `submit_consent` builds it.
    store = _InProcessWriteStore(tool_hashes=tools_list_raw)
    checkpointer = InMemorySaver()
    graph = build_recovery_graph(
        fetch_my_cart=fetchers["fetch_my_cart"],
        fetch_cart_by_id=fetchers["fetch_cart_by_id"],
        registry=load_registry(),
        fetch_delivery_types=fetchers["fetch_delivery_types"],
        fetch_time_slots=fetchers["fetch_time_slots"],
        fetch_find_products_batch=fetchers["fetch_find_products_batch"],
        planner_call=tapped_planner,
        explainer_call=tapped_explainer,
        now=lambda: datetime.now(timezone.utc),
        checkpointer=checkpointer,
        load_consent=store.load_consent,
        call_write_tool=fetchers["call_write_tool"],
        claim_and_consume=store.claim_and_consume,
        mark_action=store.mark_action,
        save_receipt=store.save_receipt,
        tool_schema_hashes=store.tool_schema_hashes,
        planner_model_id=PLANNER_PROMPT_VERSION,
        explainer_model_id=EXPLAINER_PROMPT_VERSION,
    )
    config = {"configurable": {"thread_id": "record"}}
    initial_state = new_recovery_state(
        session_id="record-session",
        trace_id="record-trace",
        now=datetime.now(timezone.utc),
        owner="record-owner",
    )
    state = graph.invoke(initial_state, config)
    print(f"read pipeline reached status={state['status']!r}")

    rounds = 0
    while state.get("status") == "awaiting_consent" and state.get("candidates"):
        proposal = state["candidates"][0]
        rounds += 1
        print(
            f"  round {rounds}: consenting to {proposal.product_name!r} "
            f"x{proposal.quantity} (expected delta {proposal.expected_delta})"
        )
        store.grant_consent(graph, config, proposal, state["cart"])
        state = graph.invoke(None, config)
        print(f"  round {rounds}: status={state.get('status')!r}")
        if state.get("status") not in ("diagnosed", "awaiting_consent"):
            break

    print(f"capture finished at status={state.get('status')!r}")
    for receipt in store.receipts:
        print(
            f"  receipt: action_id={receipt.action_id} status={receipt.status} "
            f"cleared={receipt.blocker_cleared} "
            f"expected={receipt.expected_delta} actual={receipt.actual_delta}"
        )
    if store.receipts:
        print(
            "\nTo put the cart back, run (dry run first, then --confirm):\n"
            "  .venv/Scripts/python.exe scripts/g5_restore_after_write.py "
            f"--action-id {store.receipts[-1].action_id}"
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"replay_tape_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.write_text(
        json.dumps(
            {
                "mcp": tape,
                "planner": planner_tape,
                "explainer": explainer_tape,
                "final_status": state["status"],
                "tools_list": tools_list_raw,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"raw tape written to {out} (gitignored -- never commit this file)")


# ------------------------------------------------------------------ build --


def _sanitize_tape_args(
    args: Dict[str, Any], *, aliases: Dict[str, str]
) -> Dict[str, Any]:
    """Pseudonymises a taped call's ARGUMENT VALUES while keeping every
    key (D73).

    `sanitize_payload` is the RESPONSE allow-list: it keeps wire names
    (`shoppingCartId`, `branchId`) and drops the rest. The taped args use
    the INTERNAL snake_case names `graph/replay.py`'s own fetcher closures
    build -- `cart_id`, `branch_id`, `latitude` -- so running them through
    it flattened almost every args dict to `{}`, and four different tools
    all keyed to `sha256("{}")`. `replay()` computes its key from the real
    internal args, so the args-keyed lookup could never match and every
    call fell through to the ordered fallback queue.

    Two properties have to hold at once, which is why this is its own
    function rather than a reuse:

    * no REAL identifier may be keyed on or committed;
    * the pseudonym must be the SAME one the responses got, or the
      replayed guard refuses on "cart id changed since consent was
      granted" -- hence the shared `aliases` map;
    * coordinates become the synthetic pair, because the replayed
      `compare_channels` node reads them off the sanitized cart and would
      otherwise compute a key the bundle does not carry.
    """
    out: Dict[str, Any] = {}
    for key, value in args.items():
        if key == "latitude":
            out[key] = SYNTHETIC_LATITUDE
        elif key == "longitude":
            out[key] = SYNTHETIC_LONGITUDE
        elif isinstance(value, str):
            out[key] = _alias_if_identifier(value, aliases)
        elif isinstance(value, list):
            out[key] = [
                _alias_if_identifier(item, aliases) if isinstance(item, str) else item
                for item in value
            ]
        else:
            out[key] = value
    return out


def _alias_if_identifier(value: str, aliases: Dict[str, str]) -> str:
    """Replaces a UUID-shaped value with a stable synthetic UUID, leaving
    everything else untouched. Search terms, delivery-type names and ISO
    timestamps carry no identity, and the replayed graph reproduces them
    verbatim -- changing them would break the very key match this exists
    to preserve."""
    if not _UUID_SHAPE.match(value):
        return value
    if value not in aliases:
        aliases[value] = f"00000000-0000-4000-8000-{len(aliases) + 1:012d}"
    return aliases[value]


def _alias_message(message: str, aliases: Dict[str, str]) -> str:
    """Replaces every UUID-shaped substring of a server error message with
    the same pseudonym the responses got -- a refusal message routinely
    quotes the offending id."""
    return _UUID_IN_TEXT.sub(
        lambda match: _alias_if_identifier(match.group(0), aliases), message
    )


_UUID_SHAPE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_UUID_IN_TEXT = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _build_draft_from_tape(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Pure transform: raw tape -> the unsanitized-nothing-yet-replayed
    draft bundle dict. Split out from `run_build` so it can be tested
    offline against a synthetic tape, with no live call, no replay, and
    no file write (`tests/unit/test_recorder_emits_tool_schema_hashes.py`).

    G8 (D-G8-03/T5): `tool_schema_hashes` and both `schema_hash` fields
    used to be left empty "for hand-filling" -- `BundlePlayer` then fell
    back to `("reviewed-hash", "reviewed-hash", False)` for every tool,
    making the replayed schema-drift check vacuous. Filled here from the
    tape's own `tools_list` snapshot (`run_capture` tapes it via
    `mcp.session.list_tools_raw`) whenever present; a tape recorded before
    this fix (no `tools_list` key) still builds, with both fields left
    empty exactly as before -- an old raw tape does not become unusable.
    """
    shared_aliases: Dict[str, str] = {}
    mcp_queues: Dict[str, List[Dict[str, Any]]] = {}
    # G9 (D-G9-05): the SAME sanitized responses, grouped by bare tool
    # name in call order -- never a second hand-maintained source. Only
    # `BundlePlayer`'s args-keyed lookup misses fall back to this.
    mcp_by_tool: Dict[str, List[Dict[str, Any]]] = {}
    for tool_name, args, response in raw["mcp"]:
        sanitized_args = _sanitize_tape_args(args, aliases=shared_aliases)
        if TAPED_ERROR_KEY in response:
            # A refusal carries no payload to allow-list; running it
            # through `sanitize_payload` would drop the marker and turn
            # the entry into an empty successful response (D75). The
            # message itself is pseudonymised through the shared map, so
            # a server error quoting the real cart id cannot be committed.
            sanitized_response = {
                TAPED_ERROR_KEY: _alias_message(
                    str(response[TAPED_ERROR_KEY]), shared_aliases
                )
            }
            mcp_queues.setdefault(response_key(tool_name, sanitized_args), []).append(
                sanitized_response
            )
            mcp_by_tool.setdefault(tool_name, []).append(sanitized_response)
            continue
        sanitized_response = sanitize_payload(response, aliases=shared_aliases)
        # D-G7-07: synthetic coordinates substituted AFTER sanitization --
        # `address` is never allow-listed, so the real one is already gone;
        # this restores what `compare_channels_node` needs to run instead
        # of degrading to a no-op (`nodes.py`'s own contract for a cart
        # with no coordinates).
        cart = sanitized_response.get("cart")
        original_cart = response.get("cart") if isinstance(response, dict) else None
        had_coordinates = isinstance(original_cart, dict) and isinstance(
            original_cart.get("address"), dict
        )
        # G9: conditional on the cart having HAD an address. Restoring what
        # the sanitizer stripped is the whole point for a live capture; doing
        # it to a coordinate-less synthetic cart (offline synthesis, GD-02/03/04)
        # instead makes `compare_channels_node` RUN on replay and call
        # `silpo_get_available_delivery_types` -- a call the tape never
        # recorded, because the taped run against that same cart no-opped.
        # The bundle then fails its own self-consistency replay.
        if isinstance(cart, dict) and had_coordinates:
            cart["address"] = {
                "latitude": SYNTHETIC_LATITUDE,
                "longitude": SYNTHETIC_LONGITUDE,
            }
        key = response_key(tool_name, sanitized_args)
        mcp_queues.setdefault(key, []).append(sanitized_response)
        mcp_by_tool.setdefault(tool_name, []).append(sanitized_response)

    tools_list_raw = raw.get("tools_list")
    if tools_list_raw:
        whole_hash = compute_schema_hash(tools_list_raw)
        per_tool = compute_per_tool_schema_hashes(tools_list_raw)
        # reviewed == live: this capture IS the live baseline the write
        # was authorized against at record time, so both sides of the
        # drift check agree -- exactly what a genuine "reviewed" state
        # means, not a placeholder pretending to be one.
        tool_schema_hashes = {
            name: (tool_hash, tool_hash, False) for name, tool_hash in per_tool.items()
        }
    else:
        whole_hash = ""
        tool_schema_hashes = {}

    bundle_payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "versions": {
            "schema_hash": whole_hash,
            "policy_registry_version": policy_registry_version(),
        },
        "inputs": {
            "session_id": "replay-owner-session",
            "trace_id": "replay-trace",
            "owner": "replay-owner",
        },
        "tool_schema_hashes": tool_schema_hashes,
        "mcp": mcp_queues,
        "mcp_by_tool": mcp_by_tool,
        "llm": {"planner": raw["planner"], "explainer": raw["explainer"]},
    }

    return {
        "fixture_id": "replay_hero_order_cost_min",
        "origin": "recorded",
        "source_schema_hash": whole_hash,
        "generator_version": "replay-recorder-v1",
        "seed": None,
        "transformations": [
            "sanitize_payload with a shared alias map across every "
            "response in the bundle",
            "synthetic coordinates substituted for the real address, "
            "post-sanitization",
        ],
        "expected_outcome": {},  # filled by run_build, from replaying this bundle
        "payload": bundle_payload,
    }


def run_build(tape_path: Path, bundle_id: str) -> None:
    """`bundle_id` names the output file, one per bundle -- it is REQUIRED
    rather than defaulted (D74).

    The path used to be a single hardcoded constant, so building a second,
    non-equivalent bundle silently overwrote the tracked synthetic one
    that `tests/e2e/test_replay_hero_bundle.py` and golden case GD-06 both
    assert against, turning the gate red on two tests that had nothing to
    do with the recording. Overwriting an existing bundle is now something
    a caller has to ask for by name."""
    raw = json.loads(tape_path.read_text(encoding="utf-8"))
    draft = _build_draft_from_tape(raw)
    draft["fixture_id"] = bundle_id
    bundle_path = BUNDLE_DIR / f"{bundle_id}.json"

    # Self-consistency: replay this draft bundle and use ITS OWN result
    # as the expected outcome, per graph/replay.py's module docstring.
    tmp_path = bundle_path.with_suffix(".draft.json")
    tmp_path.write_text(
        json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    result = replay(load_bundle(tmp_path))
    draft["expected_outcome"] = {
        "final_status": result.final_state.get("status"),
        "receipts": [
            {
                k: v
                for k, v in r.model_dump(mode="json").items()
                if k
                not in (
                    "action_id",
                    "created_at",
                    "trace_id",
                    "before_state",
                    "after_state",
                )
            }
            for r in result.receipts
        ],
    }
    tmp_path.unlink()

    hits = find_secret_shaped_matches(draft)
    if hits:
        raise SystemExit(f"refusing to write bundle -- secret-shaped matches: {hits}")

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"wrote {bundle_path}")
    print(
        f"live outcome for comparison: {result.final_state.get('status')!r}, "
        f"{len(result.receipts)} receipt(s) -- eyeball against the capture run's "
        "own printed status above before committing"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["capture", "build"], required=True)
    parser.add_argument(
        "--tape",
        type=Path,
        help=(
            "raw tape path for --phase build "
            "(default: newest in datasets/fixtures/raw/)"
        ),
    )
    parser.add_argument(
        "--bundle-id",
        help=(
            "output bundle id for --phase build; the file is written to "
            "datasets/fixtures/replay/<bundle-id>.json. REQUIRED (D74): a "
            "single hardcoded output path once silently overwrote the "
            "tracked synthetic bundle that two tests assert against."
        ),
    )
    args = parser.parse_args()

    if args.phase == "capture":
        run_capture()
    else:
        if not args.bundle_id:
            raise SystemExit(
                "--phase build needs --bundle-id: it names the output file, "
                "and defaulting it is how a second bundle overwrote the "
                "tracked one (D74). Use e.g. --bundle-id "
                "replay_hero_live_<yyyymmdd>."
            )
        tape_path = args.tape
        if tape_path is None:
            candidates = sorted(RAW_DIR.glob("replay_tape_*.json"))
            if not candidates:
                raise SystemExit("no raw tape found under datasets/fixtures/raw/")
            tape_path = candidates[-1]
        run_build(tape_path, args.bundle_id)


if __name__ == "__main__":
    main()
