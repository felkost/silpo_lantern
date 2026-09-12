"""the golden-case runner. Parametrized over every case file
under `datasets/golden-v1.0.0/cases/`, dispatching on each case's own
`mode` field -- `replay` runs the real compiled graph via
`graph/replay.py`, `fake_backend` uses `tests/support/write_backend.py`.

T9: a case naming a fixture the manifest lacks, an unknown `mode`, or an
`expected_outcome` key the runner cannot assert FAILS -- never skips,
never silently passes over data it cannot check.
"""

import json
from decimal import Decimal
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph.replay import load_bundle, replay
from src.lantern.graph.state import new_recovery_state
from tests.support.write_backend import (
    FakeWriteBackend,
    WriteBackendFixture,
    build_graph,
    grant_matching_consent,
)

CASES_DIR = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "cases"
MANIFEST_PATH = PROJECT_ROOT / "datasets" / "fixtures" / "manifest.json"

# The runner asserts only the `expected_outcome` keys it knows how to
# check (T9): any other key in a case's `expected_outcome` fails the case
# rather than being silently ignored.
_KNOWN_OUTCOME_KEYS = {
    "status",
    "error_contains",
    "write_calls",
    "primary_code",
    "blockers",
    "candidate_count",
    "gap",
    "receipts_count",
    "receipt_statuses",
}


def _manifest_fixture_path(fixture_id: str) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in manifest["fixtures"]:
        if entry["fixture_id"] == fixture_id:
            return PROJECT_ROOT / entry["path"]
    raise AssertionError(
        f"fixture_id {fixture_id!r} has no entry in "
        f"{MANIFEST_PATH.relative_to(PROJECT_ROOT)}"
    )


def _load_raw_cart(fixture_id: str) -> Dict[str, Any]:
    path = _manifest_fixture_path(fixture_id)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    return dict(envelope["payload"])


def _assert_expected_outcome(
    case_id: str,
    expected: Dict[str, Any],
    final_state: Dict[str, Any],
    *,
    write_calls: Any = None,
    receipts: Any = None,
) -> None:
    """`write_calls`/`receipts` are what the harness that ran the case can
    actually observe: the fake backend tracks both, `replay()` returns
    receipts but has no write-call list. A case declaring a key the
    harness that ran it cannot observe FAILS (T9) -- it is never quietly
    skipped, because "the runner could not check this" and "the runner
    checked this and it held" must not look the same in a result."""
    unknown_keys = set(expected.keys()) - _KNOWN_OUTCOME_KEYS
    if unknown_keys:
        raise AssertionError(
            f"{case_id}: expected_outcome names key(s) the runner cannot "
            f"assert: {sorted(unknown_keys)}"
        )
    if "write_calls" in expected and write_calls is None:
        raise AssertionError(
            f"{case_id}: expected_outcome declares 'write_calls', but the "
            "harness that ran this case does not track write calls"
        )
    if "receipts_count" in expected or "receipt_statuses" in expected:
        if receipts is None:
            raise AssertionError(
                f"{case_id}: expected_outcome declares a receipt assertion, "
                "but the harness that ran this case exposes no receipts"
            )
    if "status" in expected:
        assert final_state.get("status") == expected["status"], (
            f"{case_id}: expected status {expected['status']!r}, "
            f"got {final_state.get('status')!r}"
        )
    if "error_contains" in expected:
        error = final_state.get("error") or ""
        assert expected["error_contains"] in error, (
            f"{case_id}: expected error to contain "
            f"{expected['error_contains']!r}, got {error!r}"
        )
    if "write_calls" in expected:
        assert len(write_calls) == expected["write_calls"], (
            f"{case_id}: expected {expected['write_calls']} write call(s), "
            f"got {len(write_calls)}"
        )
    if "receipts_count" in expected:
        assert len(receipts) == expected["receipts_count"], (
            f"{case_id}: expected {expected['receipts_count']} receipt(s), "
            f"got {len(receipts)}"
        )
    if "receipt_statuses" in expected:
        actual_statuses = [r.status for r in receipts]
        assert actual_statuses == expected["receipt_statuses"], (
            f"{case_id}: expected receipt statuses "
            f"{expected['receipt_statuses']}, got {actual_statuses}"
        )
    if "primary_code" in expected:
        diagnosis = final_state.get("diagnosis")
        actual_primary_code = diagnosis.primary_code if diagnosis else None
        assert actual_primary_code == expected["primary_code"], (
            f"{case_id}: expected primary_code {expected['primary_code']!r}, "
            f"got {actual_primary_code!r}"
        )
    if "blockers" in expected:
        diagnosis = final_state.get("diagnosis")
        actual_blockers = (
            sorted((b.validation.code, b.is_known) for b in diagnosis.blockers)
            if diagnosis
            else []
        )
        expected_blockers = sorted(
            (b["code"], b["is_known"]) for b in expected["blockers"]
        )
        assert actual_blockers == expected_blockers, (
            f"{case_id}: expected blockers {expected_blockers}, "
            f"got {actual_blockers}"
        )
    if "gap" in expected:
        # Compared as Decimals, not strings: a golden file must not fail
        # because the recorded snapshot wrote 4.60 where the domain
        # carries 4.6 -- that is formatting, not money.
        diagnosis = final_state.get("diagnosis")
        actual_gap = diagnosis.gap if diagnosis else None
        expected_gap = Decimal(expected["gap"])
        assert (
            actual_gap is not None and Decimal(actual_gap) == expected_gap
        ), f"{case_id}: expected gap {expected_gap}, got {actual_gap}"
    if "candidate_count" in expected:
        actual_count = len(final_state.get("candidates") or [])
        assert actual_count == expected["candidate_count"], (
            f"{case_id}: expected {expected['candidate_count']} candidate(s), "
            f"got {actual_count}"
        )


def _run_fake_backend_case(case: Dict[str, Any]) -> None:
    scenario_kind = case["input"].get("scenario_kind")
    if scenario_kind is None:
        raise AssertionError(
            f"{case['case_id']}: fake_backend mode needs input.scenario_kind"
        )

    raw_cart = _load_raw_cart(case["input"]["fixture_id"])
    fixture = WriteBackendFixture(
        raw_cart=raw_cart,
        find_products_response={
            "queries": [
                {
                    "query": "Молоко «Галичина» 2,5%",
                    "products": [
                        {
                            "id": "11111111-1111-1111-1111-111111111111",
                            "name": "Молоко «Галичина» 2,5%",
                            "slug": "moloko-halychyna",
                            "price": 39.99,
                            "stock": 600,
                            "weighted": False,
                            "step": 1,
                            "available": True,
                            "companyId": "22222222-2222-2222-2222-222222222222",
                            "branchId": "33333333-3333-3333-3333-333333333333",
                            "externalProductId": 795319,
                        }
                    ],
                }
            ]
        },
    )
    backend = FakeWriteBackend(fixture)
    graph = build_graph(backend, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": f"golden-{case['case_id']}"}}
    initial_state = new_recovery_state(
        session_id="s1",
        trace_id=f"golden-{case['case_id']}",
        now=fixture.now,
        # Must match `write_backend.grant_matching_consent`'s own hardcoded
        # "owner-1"/"s1" -- a mismatch here trips authorize_write's
        # owner/session_id checks BEFORE the check a scenario actually
        # means to exercise (found by GD-12/GD-13 both failing on "owner
        # mismatch" instead of their own named reason).
        owner="owner-1",
    )
    paused_state = graph.invoke(initial_state, config)

    if scenario_kind == "diagnose_only":
        # No consent round at all -- the case is about what the read/plan
        # segment concluded, not about the write path. `paused_state` IS
        # the final state to assert against.
        final_state = paused_state
    elif scenario_kind == "no_consent":
        # Resume with no consent ever granted -- state["consent_action_id"]
        # stays unset, exercising nodes.py's own early-refusal branch.
        final_state = graph.invoke(None, config)
    elif scenario_kind in (
        "args_hash_mismatch",
        "cart_changed",
        "consent_expired",
    ):
        proposal = paused_state["candidates"][0]
        grant_matching_consent(backend, proposal)
        stored = backend.consents[proposal.action_id]

        if scenario_kind == "args_hash_mismatch":
            # The consent was granted for a DIFFERENT args_hash than what
            # the proposal will actually carry at write time -- simulates
            # a tampered or drifted consent record.
            backend.consents[proposal.action_id] = stored.model_copy(
                update={"args_hash": "tampered-hash-does-not-match"}
            )
        elif scenario_kind == "cart_changed":
            # The cart moved between consent and resume -- the guard's
            # own re-read (fetch_my_cart/fetch_cart_by_id) picks up the
            # new state, so state_hash no longer matches what consent
            # was bound to. Bump productsTotal directly on the fixture's
            # own raw_cart, which fetch_my_cart/fetch_cart_by_id read
            # from before any write has happened.
            moved_cart = dict(fixture.raw_cart)
            moved_cart["calculation"] = {
                **moved_cart["calculation"],
                "productsTotal": moved_cart["calculation"]["productsTotal"] + 50.0,
            }
            object.__setattr__(fixture, "raw_cart", moved_cart)
        elif scenario_kind == "consent_expired":
            backend.consents[proposal.action_id] = stored.model_copy(
                update={"expires_at": fixture.now - timedelta(minutes=1)}
            )

        graph.update_state(
            config,
            {
                "consent_action_id": proposal.action_id,
                "deadline": fixture.now + timedelta(seconds=90),
            },
        )
        final_state = graph.invoke(None, config)
    elif scenario_kind == "duplicate_action":
        proposal = paused_state["candidates"][0]
        grant_matching_consent(backend, proposal)
        # Simulate a prior attempt that already claimed the idempotency
        # row (a duplicate resume/retry racing itself) -- claim_and_consume
        # must return just_claimed=False on the actual attempt, so
        # write_and_readback_node reconciles via read-back rather than
        # calling the write tool a second time.
        consent = backend.consents[proposal.action_id]
        backend.journal[("owner-1", consent.cart_id, proposal.action_id)] = "in_flight"
        graph.update_state(
            config,
            {
                "consent_action_id": proposal.action_id,
                "deadline": fixture.now + timedelta(seconds=90),
            },
        )
        final_state = graph.invoke(None, config)
    else:
        raise AssertionError(
            f"{case['case_id']}: unknown scenario_kind {scenario_kind!r} -- "
            "the runner has no handling for it"
        )

    del paused_state
    _assert_expected_outcome(
        case["case_id"],
        case["expected_outcome"],
        final_state,
        write_calls=backend.write_calls,
        receipts=backend.receipts,
    )


def _run_replay_case(case: Dict[str, Any]) -> None:
    """Runs the case through `graph/replay.py` -- the REAL compiled graph
    against a recorded bundle, no MCP/LLM/Postgres call. `input.fixture_id`
    must name a bundle in the manifest, not a bare cart snapshot: a bundle
    carries the ordered MCP/LLM response queues `replay()` needs, which a
    cart fixture alone cannot supply."""
    path = _manifest_fixture_path(case["input"]["fixture_id"])
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if "mcp" not in (envelope.get("payload") or {}):
        raise AssertionError(
            f"{case['case_id']}: fixture "
            f"{case['input']['fixture_id']!r} is not a replay bundle "
            "(its payload carries no 'mcp' response queues)"
        )

    bundle = load_bundle(path)
    result = replay(bundle)
    _assert_expected_outcome(
        case["case_id"],
        case["expected_outcome"],
        dict(result.final_state),
        receipts=result.receipts,
    )


def _run_case(case: Dict[str, Any]) -> None:
    mode = case.get("mode")
    if mode == "fake_backend":
        _run_fake_backend_case(case)
    elif mode == "replay":
        _run_replay_case(case)
    else:
        raise AssertionError(f"{case['case_id']}: unknown mode {mode!r}")


def _case_files():
    if not CASES_DIR.exists():
        return []
    return sorted(CASES_DIR.glob("*.json"))


@pytest.mark.parametrize("case_path", _case_files(), ids=lambda p: p.stem)
def test_golden_case(case_path: Path) -> None:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    _run_case(case)


def test_at_least_one_case_exists() -> None:
    assert _case_files(), "no case files found under " + str(CASES_DIR)


def test_a_case_naming_an_unknown_fixture_fails() -> None:
    case = {
        "case_id": "SYNTHETIC-BAD-FIXTURE",
        "input": {"fixture_id": "no-such-fixture-id", "scenario_kind": "no_consent"},
        "expected_outcome": {"status": "aborted"},
        "mode": "fake_backend",
    }
    with pytest.raises(AssertionError):
        _run_case(case)


def test_a_case_with_an_unknown_mode_fails() -> None:
    case = {
        "case_id": "SYNTHETIC-BAD-MODE",
        "input": {"fixture_id": "golden_safety_baseline"},
        "expected_outcome": {},
        "mode": "not_a_real_mode",
    }
    with pytest.raises(AssertionError):
        _run_case(case)


def test_a_replay_case_naming_a_plain_cart_fixture_fails() -> None:
    """A cart snapshot is not a bundle -- it carries no recorded MCP/LLM
    response queues, so `replay()` cannot drive the graph from it. Caught
    with a named reason rather than a KeyError deep inside load_bundle."""
    case = {
        "case_id": "SYNTHETIC-CART-NOT-BUNDLE",
        "input": {"fixture_id": "golden_safety_baseline"},
        "expected_outcome": {},
        "mode": "replay",
    }
    with pytest.raises(AssertionError, match="not a replay bundle"):
        _run_case(case)


def test_a_replay_case_declaring_write_calls_fails() -> None:
    """`replay()` exposes receipts but tracks no write-call list, so a
    case asserting `write_calls` against it must fail rather than pass
    vacuously -- "could not check" and "checked, held" must never look
    the same in a result."""
    case = {
        "case_id": "SYNTHETIC-REPLAY-WRITE-CALLS",
        "input": {"fixture_id": "replay_hero_order_cost_min"},
        "expected_outcome": {"write_calls": 0},
        "mode": "replay",
    }
    with pytest.raises(AssertionError, match="does not track write calls"):
        _run_case(case)


def test_a_fake_backend_case_declaring_receipt_statuses_is_supported() -> None:
    """The fake backend DOES collect receipts, so a receipt assertion is
    checkable there -- the guard above is about what a harness can
    observe, not a blanket ban on the key."""
    case = {
        "case_id": "SYNTHETIC-FAKE-RECEIPTS",
        "input": {
            "fixture_id": "golden_safety_baseline",
            "scenario_kind": "duplicate_action",
        },
        "expected_outcome": {"receipts_count": 1},
        "mode": "fake_backend",
    }
    _run_case(case)


def test_a_case_with_an_unassertable_expected_outcome_key_fails() -> None:
    case = {
        "case_id": "SYNTHETIC-BAD-OUTCOME-KEY",
        "input": {
            "fixture_id": "golden_safety_baseline",
            "scenario_kind": "no_consent",
        },
        "expected_outcome": {"totally_made_up_key": "x"},
        "mode": "fake_backend",
    }
    with pytest.raises(AssertionError):
        _run_case(case)
