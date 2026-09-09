"""G7 (D-G7-06/D-G7-07): records a LIVE hero run into a tracked replay
bundle at `datasets/fixtures/replay/hero_order_cost_min.json` -- the
live-recorded upgrade of the synthetic bundle
`tests/e2e/test_replay_hero_bundle.py` already proves the mechanism
against (built from `tests/unit/test_write_path_interrupt_and_resume.py`'s
own synthetic fixture, `origin: synthetic`, not a live capture).

Two phases, run separately:

  --phase capture   Live: taps every MCP fetcher and the REAL planner/
                     explainer LLM calls around a full hero run --
                     including the write and, if the author drives a
                     second consent round by hand, that too. Writes the
                     raw, UNSANITIZED tape to the gitignored
                     `datasets/fixtures/raw/replay_tape_<timestamp>.json`.
                     Costs a live LLM call and a live MCP write --
                     needs the author's explicit go-ahead, shown as the
                     exact command before it runs (CLAUDE.md section 8).

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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from src.lantern.config import (  # noqa: E402
    PROJECT_ROOT,
    get_openrouter_api_key,
    load_env,
)
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
from src.lantern.graph.state import new_recovery_state  # noqa: E402
from src.lantern.mcp.auth import (  # noqa: E402
    DiskTokenStorage,
    build_redirect_handler,
    callback_handler,
)
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
BUNDLE_PATH = (
    PROJECT_ROOT / "datasets" / "fixtures" / "replay" / "hero_order_cost_min.json"
)
# Synthetic replacement for any real address -- never the real coordinates
# at any stage, per sanitizer.py's own rule that `address` is never
# allow-listed. Kyiv city-centre, not the author's real delivery point.
SYNTHETIC_LATITUDE = 50.45
SYNTHETIC_LONGITUDE = 30.52


# ---------------------------------------------------------------- capture --


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
        resp = _sync_call("silpo_get_my_shopping_cart", args)
        tape.append(("silpo_get_my_shopping_cart", args, resp))
        return resp

    def fetch_cart_by_id(cart_id: str) -> Dict[str, Any]:
        resp = _sync_call("silpo_get_shopping_cart_by_id", {"shoppingCartId": cart_id})
        args = {"cart_id": cart_id}
        tape.append(("silpo_get_shopping_cart_by_id", args, resp))
        return resp

    def fetch_delivery_types(latitude: float, longitude: float) -> Dict[str, Any]:
        resp = _sync_call(
            "silpo_get_available_delivery_types",
            {"latitude": latitude, "longitude": longitude},
        )
        args = {"latitude": latitude, "longitude": longitude}
        tape.append(("silpo_get_available_delivery_types", args, resp))
        return resp

    def fetch_time_slots(
        branch_id: str, delivery_types: Sequence[str]
    ) -> Dict[str, Any]:
        resp = _sync_call(
            "silpo_get_time_slots",
            {"branchId": branch_id, "deliveryTypes": list(delivery_types)},
        )
        args = {"branch_id": branch_id, "delivery_types": list(delivery_types)}
        tape.append(("silpo_get_time_slots", args, resp))
        return resp

    def fetch_find_products_batch(
        branch_id: str, delivery_type: str, start: str, end: str, names: Sequence[str]
    ) -> Dict[str, Any]:
        resp = _sync_call(
            "silpo_find_products_batch",
            {
                "branchId": branch_id,
                "deliveryType": delivery_type,
                "start": start,
                "end": end,
                "names": list(names),
            },
        )
        args = {
            "branch_id": branch_id,
            "delivery_type": delivery_type,
            "start": start,
            "end": end,
            "names": list(names),
        }
        tape.append(("silpo_find_products_batch", args, resp))
        return resp

    def call_write_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        resp = _sync_call(tool_name, args)
        tape.append((tool_name, dict(args), resp))
        return resp

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
    planner_llm = build_planner_llm(models_config["planner"]["model"], key)
    explainer_llm = build_explainer_llm(explainer_model, key)
    raw_planner_call = make_planner_call(planner_llm)
    raw_explainer_call = make_explainer_call(explainer_llm)

    def tapped_planner(state: Any) -> Any:
        intent = raw_planner_call(state)
        planner_tape.append(intent.model_dump(mode="json"))
        return intent

    def tapped_explainer(proposal: Any) -> Any:
        output = raw_explainer_call(proposal)
        explainer_tape.append(output.model_dump(mode="json"))
        return output

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
        planner_model_id=PLANNER_PROMPT_VERSION,
        explainer_model_id=EXPLAINER_PROMPT_VERSION,
    )
    initial_state = new_recovery_state(
        session_id="record-session",
        trace_id="record-trace",
        now=datetime.now(timezone.utc),
        owner="record-owner",
    )
    state = graph.invoke(initial_state, {"configurable": {"thread_id": "record"}})
    print(f"read pipeline reached status={state['status']!r}")
    print(
        "This script's --phase capture stops here: it proves the read "
        "chain and drives no write. The consent + write round (and any "
        "second round) is driven by the author through the real API, "
        "with `call_write_tool` above taping it -- see the stage spec "
        "for the exact command sequence, shown before each run."
    )

    # G8 (D-G8-03/T5): a live `tools/list` snapshot, taped alongside the
    # MCP/LLM calls -- without it, `run_build` had nothing to compute
    # `tool_schema_hashes`/`schema_hash` from and left both empty for
    # hand-filling, which made `BundlePlayer`'s replayed drift check
    # vacuous (it fell back to `("reviewed-hash", "reviewed-hash",
    # False)` for every tool, per `graph/replay.py`).
    print("  MCP call: tools/list")
    tools_list_raw = list_tools_raw(server_url=DEFAULT_MCP_URL)

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
    for tool_name, args, response in raw["mcp"]:
        sanitized_args = sanitize_payload(args, aliases=shared_aliases)
        sanitized_response = sanitize_payload(response, aliases=shared_aliases)
        # D-G7-07: synthetic coordinates substituted AFTER sanitization --
        # `address` is never allow-listed, so the real one is already gone;
        # this restores what `compare_channels_node` needs to run instead
        # of degrading to a no-op (`nodes.py`'s own contract for a cart
        # with no coordinates).
        cart = sanitized_response.get("cart")
        if isinstance(cart, dict):
            cart["address"] = {
                "latitude": SYNTHETIC_LATITUDE,
                "longitude": SYNTHETIC_LONGITUDE,
            }
        key = response_key(tool_name, sanitized_args)
        mcp_queues.setdefault(key, []).append(sanitized_response)

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


def run_build(tape_path: Path) -> None:
    raw = json.loads(tape_path.read_text(encoding="utf-8"))
    draft = _build_draft_from_tape(raw)

    # Self-consistency: replay this draft bundle and use ITS OWN result
    # as the expected outcome, per graph/replay.py's module docstring.
    tmp_path = BUNDLE_PATH.with_suffix(".draft.json")
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

    BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUNDLE_PATH.write_text(
        json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"wrote {BUNDLE_PATH}")
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
    args = parser.parse_args()

    if args.phase == "capture":
        run_capture()
    else:
        tape_path = args.tape
        if tape_path is None:
            candidates = sorted(RAW_DIR.glob("replay_tape_*.json"))
            if not candidates:
                raise SystemExit("no raw tape found under datasets/fixtures/raw/")
            tape_path = candidates[-1]
        run_build(tape_path)


if __name__ == "__main__":
    main()
