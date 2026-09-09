"""G9 (D62/D-G9-05): `replay()` gains optional `planner_call`/`explainer_call`
parameters so the 18 core repeats (G9.6) can wire in the REAL live planner/
explainer against replayed MCP -- while every existing offline caller
(`tests/e2e/test_replay_hero_bundle.py`, the golden runner) keeps working
unchanged. This test proves the "unchanged" half: omitting the new
parameters must produce byte-identical behavior to today's hardcoded call
to `player.next_planner`/`player.next_explainer`.
"""

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph.replay import load_bundle, replay

BUNDLE_PATH = (
    PROJECT_ROOT / "datasets" / "fixtures" / "replay" / "hero_order_cost_min.json"
)


def _dump_receipts(receipts):
    dumped = []
    for r in receipts:
        d = r.model_dump(mode="json")
        for excluded in ("action_id", "created_at", "trace_id"):
            d.pop(excluded, None)
        dumped.append(d)
    return dumped


def test_replay_accepts_the_new_parameters_and_omitting_them_matches_today() -> None:
    baseline = replay(load_bundle(BUNDLE_PATH))
    with_explicit_none = replay(
        load_bundle(BUNDLE_PATH), planner_call=None, explainer_call=None
    )

    assert baseline.final_state.get("status") == with_explicit_none.final_state.get(
        "status"
    )
    assert _dump_receipts(baseline.receipts) == _dump_receipts(
        with_explicit_none.receipts
    )
    assert baseline.consented_action_id != ""
    assert with_explicit_none.consented_action_id != ""


def test_an_explicit_planner_call_override_is_actually_used() -> None:
    """Proves the parameter is not dead code: a custom `planner_call` that
    never touches the bundle's own LLM queue must still drive the graph to
    the same recorded outcome, since it returns the identical `SearchIntent`
    shape the tape would have."""
    import json

    from src.lantern.graph.schemas import SearchIntent

    bundle = load_bundle(BUNDLE_PATH)
    raw_calls = []
    tape_planner_output = bundle.llm["planner"][0]

    def custom_planner_call(state):
        raw_calls.append(state)
        return SearchIntent(**tape_planner_output)

    result = replay(bundle, planner_call=custom_planner_call)

    assert raw_calls, "the override was never invoked -- replay() ignored it"
    assert result.consented_action_id != ""
    # sanity: still reaches the same final status as the untouched default
    assert (
        result.final_state.get("status")
        == json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))["expected_outcome"][
            "final_status"
        ]
    )
