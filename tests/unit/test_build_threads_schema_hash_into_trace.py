"""Closes the Definition-of-Done requirement that a server/release/schema
hash and app/prompt/policy/model versions appear in the trace: `build.py`
constructs `version_tuple` from its own `tools_schema_hash` parameter and
passes it to `traced_llm_call` for BOTH the planner and explainer calls —
this test proves that wiring end to end without needing live tracing
enabled, by spying on `traced_llm_call` itself rather than on a real
LangSmith run.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import patch

from src.lantern.graph.build import build_recovery_graph
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.policies.loader import load_registry


def _noop_planner(state: Any) -> SearchIntent:
    return SearchIntent(search_terms=["x"])


def _noop_explainer(proposal: Any) -> ExplainerOutput:
    return ExplainerOutput(action_id="a1", guest_text_uk="x")


def test_tools_schema_hash_reaches_both_the_planner_and_explainer_trace() -> None:
    calls: List[Dict[str, Any]] = []

    def spy_traced_llm_call(name, fn, process_inputs, version_tuple=None, tags=None):
        calls.append({"name": name, "version_tuple": version_tuple})
        return fn

    with patch(
        "src.lantern.graph.build.traced_llm_call", side_effect=spy_traced_llm_call
    ):
        build_recovery_graph(
            fetch_my_cart=lambda: {},
            fetch_cart_by_id=lambda cart_id: {},
            registry=load_registry(),
            fetch_delivery_types=lambda lat, lon: {},
            fetch_time_slots=lambda branch_id, types: {},
            fetch_find_products_batch=lambda *a, **kw: {},
            planner_call=_noop_planner,
            explainer_call=_noop_explainer,
            now=lambda: datetime.now(timezone.utc),
            planner_model_id="google/gemini-3.8-flash",
            explainer_model_id="google/gemini-3.5-flash-lite",
            tools_schema_hash="abc123def456",
        )

    names = {c["name"] for c in calls}
    assert names == {"planner", "explainer"}
    for call in calls:
        assert call["version_tuple"]["schema_hash"] == "abc123def456"
        assert call["version_tuple"]["policy_registry_version"] != ""

    planner_tuple = next(c["version_tuple"] for c in calls if c["name"] == "planner")
    explainer_tuple = next(
        c["version_tuple"] for c in calls if c["name"] == "explainer"
    )
    assert planner_tuple["planner_model_id"] == "google/gemini-3.8-flash"
    assert explainer_tuple["explainer_model_id"] == "google/gemini-3.5-flash-lite"


def test_an_empty_schema_hash_still_reaches_the_trace_explicitly() -> None:
    """A caller that never learned the live schema hash gets an explicit
    empty string in the trace, not a missing key — the DoD line is about
    the field being PRESENT, and a silently-absent key would be harder to
    notice missing than an empty one."""
    calls: List[Dict[str, Any]] = []

    def spy_traced_llm_call(name, fn, process_inputs, version_tuple=None, tags=None):
        calls.append(version_tuple)
        return fn

    with patch(
        "src.lantern.graph.build.traced_llm_call", side_effect=spy_traced_llm_call
    ):
        build_recovery_graph(
            fetch_my_cart=lambda: {},
            fetch_cart_by_id=lambda cart_id: {},
            registry=load_registry(),
            fetch_delivery_types=lambda lat, lon: {},
            fetch_time_slots=lambda branch_id, types: {},
            fetch_find_products_batch=lambda *a, **kw: {},
            planner_call=_noop_planner,
            explainer_call=_noop_explainer,
            now=lambda: datetime.now(timezone.utc),
        )

    for version_tuple in calls:
        assert "schema_hash" in version_tuple
        assert version_tuple["schema_hash"] == ""


def test_trace_tags_reach_both_the_planner_and_explainer_call() -> None:
    """A run with no tags is indistinguishable from any other in the
    LangSmith UI — this is what lets a caller (e.g. a live-run script)
    mark its own traces so they can be filtered later, same as
    `scripts/ua_eval_run.py` already does for its own raw LLM calls."""
    calls: List[Dict[str, Any]] = []

    def spy_traced_llm_call(name, fn, process_inputs, version_tuple=None, tags=None):
        calls.append({"name": name, "tags": tags})
        return fn

    with patch(
        "src.lantern.graph.build.traced_llm_call", side_effect=spy_traced_llm_call
    ):
        build_recovery_graph(
            fetch_my_cart=lambda: {},
            fetch_cart_by_id=lambda cart_id: {},
            registry=load_registry(),
            fetch_delivery_types=lambda lat, lon: {},
            fetch_time_slots=lambda branch_id, types: {},
            fetch_find_products_batch=lambda *a, **kw: {},
            planner_call=_noop_planner,
            explainer_call=_noop_explainer,
            now=lambda: datetime.now(timezone.utc),
            trace_tags=["g4-live", "criterion-8"],
        )

    for call in calls:
        assert call["tags"] == ["g4-live", "criterion-8"]
