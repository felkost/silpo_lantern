"""G9 (G9.2, step 1.4): builds a replay bundle OFFLINE, by taping a graph
run against `tests/support/write_backend.py`'s fake backend instead of the
live MCP server.

Why this exists: `record_replay_bundle.py` tapes a LIVE run, and needs the
author's go-ahead for a real MCP write. The core golden cases GD-02/03/04
each need their own bundle (they run in `replay` mode so they can join
G9.6's 18 repeats, which drive `replay()` with a live planner), but their
INPUT is a seeded synthetic cart -- there is nothing live to record. This
script produces a bundle from such a cart deterministically, at no cost.

Reuses `record_replay_bundle._build_draft_from_tape` verbatim rather than
re-implementing the tape->bundle transform, so a synthesized bundle and a
live-recorded one are built by exactly the same code path (including the
sanitizer and the `mcp_by_tool` fallback queue, D-G9-05).

The written bundle is self-consistent by construction: it is replayed
before it is written, and its own replay result becomes its
`expected_outcome` -- the same rule `run_build` applies to a live tape.

Offline, deterministic, no network, no cost. Not part of the gate --
run by hand when a new core golden case needs a bundle.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from scripts.record_replay_bundle import _build_draft_from_tape  # noqa: E402
from src.lantern.config import PROJECT_ROOT  # noqa: E402
from src.lantern.graph.build import build_recovery_graph  # noqa: E402
from src.lantern.graph.replay import load_bundle, replay  # noqa: E402
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent  # noqa: E402
from src.lantern.graph.state import (  # noqa: E402
    ACTIVE_EXECUTION_SECONDS,
    new_recovery_state,
)
from scripts.sanitize_fixture import find_secret_shaped_matches  # noqa: E402
from src.lantern.policies.loader import load_registry  # noqa: E402
from tests.support.write_backend import (  # noqa: E402
    FakeWriteBackend,
    WriteBackendFixture,
    grant_matching_consent,
)

MANIFEST_PATH = PROJECT_ROOT / "datasets" / "fixtures" / "manifest.json"
BUNDLE_DIR = PROJECT_ROOT / "datasets" / "fixtures" / "replay"


def _manifest_fixture_path(fixture_id: str) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in manifest["fixtures"]:
        if entry["fixture_id"] == fixture_id:
            return PROJECT_ROOT / entry["path"]
    raise SystemExit(f"fixture_id {fixture_id!r} is not in the manifest")


def _load_raw_cart(fixture_id: str) -> Dict[str, Any]:
    envelope = json.loads(
        _manifest_fixture_path(fixture_id).read_text(encoding="utf-8")
    )
    return dict(envelope["payload"])


def _tapped_graph(
    backend: FakeWriteBackend,
    tape: List[Tuple[str, Dict[str, Any], Dict[str, Any]]],
    planner_tape: List[Dict[str, Any]],
    explainer_tape: List[Dict[str, Any]],
    checkpointer: Any,
) -> Any:
    """Same boundaries `write_backend.build_graph` binds, each wrapped so
    the call is recorded in the `(tool_name, args, response)` shape
    `_build_draft_from_tape` expects -- args shaped exactly as
    `graph/replay.py`'s own fetcher closures build them, so the
    `response_key` computed at build time matches what `replay()` computes
    later."""
    fixture = backend.fixture

    def fetch_my_cart() -> Dict[str, Any]:
        resp = {"shoppingCartId": fixture.raw_cart["id"]}
        tape.append(("silpo_get_my_shopping_cart", {}, resp))
        return resp

    def fetch_cart_by_id(cart_id: str) -> Dict[str, Any]:
        resp = (
            backend.fetch_cart_by_id_after_write(cart_id)
            if backend.write_side_effect_applied
            else {"cart": fixture.raw_cart}
        )
        tape.append(("silpo_get_shopping_cart_by_id", {"cart_id": cart_id}, resp))
        return resp

    def fetch_delivery_types(latitude: float, longitude: float) -> Dict[str, Any]:
        resp = fixture.delivery_types_response
        tape.append(
            (
                "silpo_get_available_delivery_types",
                {"latitude": latitude, "longitude": longitude},
                resp,
            )
        )
        return resp

    def fetch_time_slots(branch_id: str, delivery_types: Any) -> Dict[str, Any]:
        resp = fixture.time_slots_response
        tape.append(
            (
                "silpo_get_time_slots",
                {"branch_id": branch_id, "delivery_types": list(delivery_types)},
                resp,
            )
        )
        return resp

    def fetch_find_products_batch(
        branch_id: str, delivery_type: str, start: str, end: str, names: Any
    ) -> Dict[str, Any]:
        resp = fixture.find_products_response
        tape.append(
            (
                "silpo_find_products_batch",
                {
                    "branch_id": branch_id,
                    "delivery_type": delivery_type,
                    "start": start,
                    "end": end,
                    "names": list(names),
                },
                resp,
            )
        )
        return resp

    def call_write_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        resp = backend.call_write_tool(tool_name, args)
        tape.append((tool_name, dict(args), resp))
        return resp

    def planner_call(state: Any) -> SearchIntent:
        intent = SearchIntent(search_terms=list(fixture.search_terms))
        planner_tape.append(intent.model_dump(mode="json"))
        return intent

    def explainer_call(proposal: Any) -> ExplainerOutput:
        out = ExplainerOutput(
            action_id=proposal.action_id, guest_text_uk="Додати товар"
        )
        explainer_tape.append(out.model_dump(mode="json"))
        return out

    return build_recovery_graph(
        fetch_my_cart=fetch_my_cart,
        fetch_cart_by_id=fetch_cart_by_id,
        registry=load_registry(),
        fetch_delivery_types=fetch_delivery_types,
        fetch_time_slots=fetch_time_slots,
        fetch_find_products_batch=fetch_find_products_batch,
        planner_call=planner_call,
        explainer_call=explainer_call,
        now=lambda: fixture.now,
        checkpointer=checkpointer,
        load_consent=backend.load_consent,
        call_write_tool=call_write_tool,
        claim_and_consume=backend.claim_and_consume,
        mark_action=backend.mark_action,
        save_receipt=backend.save_receipt,
        tool_schema_hashes=backend.tool_schema_hashes,
    )


def synthesize(
    fixture_id: str,
    find_products_response: Dict[str, Any],
    applied_price_ratio: float = 1.0,
) -> Dict[str, Any]:
    """Runs the graph to completion against the fake backend, consenting
    to the first candidate of every round the graph offers (mirroring
    `replay()`'s own consent loop), and returns the draft bundle.

    `applied_price_ratio` < 1.0 reproduces D68's measured live effect (the
    cart applies a loyalty discount the catalogue does not report), which
    is what makes a genuine two-round scenario reachable."""
    fixture = WriteBackendFixture(
        raw_cart=_load_raw_cart(fixture_id),
        find_products_response=find_products_response,
        applied_price_ratio=applied_price_ratio,
    )
    backend = FakeWriteBackend(fixture)
    tape: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    planner_tape: List[Dict[str, Any]] = []
    explainer_tape: List[Dict[str, Any]] = []

    graph = _tapped_graph(backend, tape, planner_tape, explainer_tape, InMemorySaver())
    config = {"configurable": {"thread_id": f"synth-{fixture_id}"}}
    state = graph.invoke(
        new_recovery_state(
            session_id="s1",
            trace_id=f"synth-{fixture_id}",
            now=fixture.now,
            owner="owner-1",
        ),
        config,
    )
    while state.get("status") == "awaiting_consent" and state.get("candidates"):
        proposal = state["candidates"][0]
        grant_matching_consent(backend, proposal)
        graph.update_state(
            config,
            {
                "consent_action_id": proposal.action_id,
                "deadline": fixture.now + timedelta(seconds=ACTIVE_EXECUTION_SECONDS),
            },
        )
        state = graph.invoke(None, config)
        if state.get("status") not in ("diagnosed", "awaiting_consent"):
            break

    raw = {
        "mcp": tape,
        "planner": planner_tape,
        "explainer": explainer_tape,
        "final_status": state.get("status"),
    }
    return _build_draft_from_tape(raw)


def write_bundle(draft: Dict[str, Any], bundle_id: str) -> Path:
    """Replays the draft BEFORE writing it, and uses its own replay result
    as `expected_outcome` -- the same self-consistency rule `run_build`
    applies to a live tape. A draft that cannot replay is never written."""
    draft["fixture_id"] = bundle_id
    draft["origin"] = "synthetic"
    draft["generator_version"] = "synthesize-replay-bundle-v1"

    out_path = BUNDLE_DIR / f"{bundle_id}.json"
    tmp_path = out_path.with_suffix(".draft.json")
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
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

    out_path.write_text(
        json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"wrote {out_path.relative_to(PROJECT_ROOT)} -- "
        f"replays to {result.final_state.get('status')!r} with "
        f"{len(result.receipts)} receipt(s)"
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-id", required=True, help="cart fixture to build from"
    )
    parser.add_argument("--bundle-id", required=True, help="output bundle fixture_id")
    parser.add_argument(
        "--products-json",
        required=True,
        help="path to a JSON file holding the find_products_batch response",
    )
    parser.add_argument(
        "--applied-price-ratio",
        type=float,
        default=1.0,
        help=(
            "fraction of the catalogue price the cart actually applies "
            "(D68: Silpo's own loyalty discount measured at ~0.90 live)"
        ),
    )
    args = parser.parse_args()

    products = json.loads(Path(args.products_json).read_text(encoding="utf-8"))
    draft = synthesize(args.fixture_id, products, args.applied_price_ratio)
    write_bundle(draft, args.bundle_id)


if __name__ == "__main__":
    main()
