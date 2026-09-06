"""`config/models.yaml` ("кошик моделей") has no
dedicated loader — same convention as `config/mutation_matrix.yaml`
(read directly with `yaml.safe_load` at the point of use). This is the
one check that stands between a typo in the YAML and it going unnoticed
until a live run fails on it.
"""

from pathlib import Path

import yaml

from src.lantern.config import PROJECT_ROOT

MODELS_YAML_PATH = PROJECT_ROOT / "config" / "models.yaml"


def _load() -> dict:
    return yaml.safe_load(Path(MODELS_YAML_PATH).read_text(encoding="utf-8"))


def test_the_file_parses_as_valid_yaml() -> None:
    data = _load()
    assert isinstance(data, dict)


def test_top_level_sections_are_present() -> None:
    data = _load()
    for key in ("planner", "explainer", "eval_judge", "budgets", "degradation_order"):
        assert key in data, f"missing top-level key: {key}"


def test_budgets_match_the_enforced_values_in_graph_state() -> None:
    """These two files declare the same budget numbers in two
    different places (a YAML config a human reads, and Python constants
    the graph actually enforces) — this test is what stops them drifting
    apart silently."""
    from src.lantern.graph.state import (
        ACTIVE_EXECUTION_SECONDS,
        MAX_CYCLES,
        MAX_MCP_ATTEMPTS,
        MAX_TOKENS,
    )

    budgets = _load()["budgets"]
    assert budgets["max_cycles"] == MAX_CYCLES
    assert budgets["max_mcp_attempts"] == MAX_MCP_ATTEMPTS
    assert budgets["max_tokens"] == MAX_TOKENS
    assert budgets["active_execution_seconds"] == ACTIVE_EXECUTION_SECONDS


def test_explainer_is_decided_by_ua_eval_judge_stays_undecided() -> None:
    """`explainer.selected` is decided only after UA-Eval's live run;
    `eval_judge.selected` is a separate, still-undecided choice — a value
    for either before its own run would be an invented fact, not a
    decision.
    """
    data = _load()
    # UA-Eval's full run settled the explainer pick — the only
    # candidate that cleared the threshold with complete data.
    assert data["explainer"]["selected"] == "google/gemini-3.5-flash-lite"
    # eval_judge itself stays undecided — this run only used grok-4.6 as
    # the cheaper of the two candidates to SCORE the explainer candidates,
    # it never compared the two judge candidates against each other.
    assert data["eval_judge"]["selected"] is None
    assert data["eval_judge"]["calibrated"] is False


def test_planner_model_is_a_real_looking_openrouter_id() -> None:
    data = _load()
    assert "/" in data["planner"]["model"]


def test_planner_context_window_exceeds_explainer_matching_the_unit_economics() -> None:
    """Author-requested design constraint: the infrequent, context-heavy
    planner call needs more context-window headroom than the frequent,
    narrow explainer call — this test is what stops the two config blocks
    drifting into an inverted (and wasteful, or worse, truncating) shape."""
    data = _load()
    planner_window = data["planner"]["context_window_min_tokens"]
    explainer_window = data["explainer"]["context_window_min_tokens"]
    assert planner_window > explainer_window

    planner_expected_input = data["planner"]["expected_tokens"]["input"]
    explainer_expected_input = data["explainer"]["expected_tokens"]["input"]
    assert planner_window > planner_expected_input
    assert explainer_window > explainer_expected_input
