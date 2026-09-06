"""Wires the node functions in `nodes.py` into an actual LangGraph
`StateGraph`. Real API, probed directly against the installed SDK before
use, not assumed from documentation: `StateGraph(RecoveryState)`,
`.add_node`, `.add_conditional_edges`, `.set_entry_point`,
`.compile(checkpointer=...)`.

Every MCP/LLM call is injected — see `nodes.py`'s own module docstring for
why. `build_recovery_graph` is the one place all of them come together;
nothing here performs I/O itself.
"""

import hashlib
from datetime import datetime
from typing import Any, Callable, Mapping, Optional, Sequence

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.lantern.graph.nodes import (
    make_collect_and_gate_node,
    make_compare_channels_node,
    make_diagnose_node,
    make_explain_node,
    make_plan_node,
    make_read_node,
    rank_node,
)
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.graph.state import RecoveryState
from src.lantern.observability.tracer import (
    redact_explainer_input,
    redact_planner_input,
    traced_llm_call,
)
from src.lantern.policies.loader import DEFAULT_REGISTRY_PATH, PolicyRegistry


def policy_registry_version() -> str:
    """A short content hash of `registry.yaml`, used as the "policy"
    element of the version tuple that must appear in the trace — hashing
    the tracked file rather than adding a new field to it, since the
    registry/schema files are already closed and tested and
    `registry.schema.json` has `additionalProperties: false` at the top
    level (a new field would need a schema change this stage does not own).
    """
    return hashlib.sha256(DEFAULT_REGISTRY_PATH.read_bytes()).hexdigest()[:12]


def _add_node(graph: Any, name: str, node: Any) -> None:
    """`graph`/`node` typed `Any` on purpose: `StateGraph.add_node`'s
    overloads bind `NodeInputT` from a `Runnable`/dataclass-like protocol
    and cannot unify a plain closure typed `Callable[[RecoveryState],
    Dict[str, Any]]` against it — a static typing friction point in the
    installed SDK's own stubs, not a real type error. `tests/unit/
    test_graph_pipeline_reaches_awaiting_consent.py` proves at runtime
    every one of these plain functions works exactly as `add_node`
    documents; routing every `add_node` call through this one narrowly-Any
    function keeps the escape hatch in one place instead of a `type:
    ignore` repeated at every call site.
    """
    graph.add_node(name, node)


def _continue_or_end(state: RecoveryState) -> str:
    """The one routing rule shared by every fail-safe exit point (the write
    route is a separate, deliberate dead end — this is about
    `CartShapeError`/missing-precondition aborts, not consent): a node that
    set `status="aborted"` ends the graph immediately; anything else
    continues to the next step.
    """
    return "end" if state["status"] == "aborted" else "continue"


def build_recovery_graph(
    fetch_my_cart: Callable[[], Mapping[str, Any]],
    fetch_cart_by_id: Callable[[str], Mapping[str, Any]],
    registry: PolicyRegistry,
    fetch_delivery_types: Callable[[float, float], Mapping[str, Any]],
    fetch_time_slots: Callable[[str, Sequence[str]], Mapping[str, Any]],
    fetch_find_products_batch: Callable[
        [str, str, str, str, Sequence[str]], Mapping[str, Any]
    ],
    planner_call: Callable[[RecoveryState], SearchIntent],
    explainer_call: Callable[[Any], ExplainerOutput],
    now: Callable[[], datetime],
    checkpointer: Optional[Any] = None,
    planner_model_id: str = "",
    explainer_model_id: str = "",
    tools_schema_hash: str = "",
    trace_tags: Optional[Sequence[str]] = None,
) -> "CompiledStateGraph[RecoveryState, Any, RecoveryState, RecoveryState]":
    """Builds the compiled graph for this slice: read -> diagnose ->
    compare_channels -> plan -> collect_and_gate -> rank -> explain ->
    `awaiting_consent`. `compare_channels` never aborts by itself (a cart
    with no coordinates, or a channel with no valid slots, degrades that
    one channel/the whole comparison rather than the recovery) — every
    other step can abort on a `CartShapeError` or a missing precondition.

    `planner_call`/`explainer_call` are wrapped with `traced_llm_call`
    before reaching their node factories — every LLM call this graph makes
    carries the required version tuple, not just the ones a developer
    remembers to annotate by hand. The three `*_model_id`/`tools_schema_hash`
    parameters
    default to empty strings so tests that don't care about tracing (most
    of them — see `test_graph_pipeline_reaches_awaiting_consent.py`) don't
    need to supply them.
    """
    graph = StateGraph(RecoveryState)

    version_tuple = {
        "schema_hash": tools_schema_hash,
        "policy_registry_version": policy_registry_version(),
        "planner_model_id": planner_model_id,
        "planner_prompt_version": "planner_v1",
        "explainer_model_id": explainer_model_id,
        "explainer_prompt_version": "explainer_v1",
    }
    traced_planner_call = traced_llm_call(
        "planner", planner_call, redact_planner_input, version_tuple, trace_tags
    )
    traced_explainer_call = traced_llm_call(
        "explainer", explainer_call, redact_explainer_input, version_tuple, trace_tags
    )

    read_node = make_read_node(fetch_my_cart, fetch_cart_by_id)
    diagnose_node = make_diagnose_node(registry)
    compare_channels_node = make_compare_channels_node(
        fetch_delivery_types, fetch_time_slots, fetch_find_products_batch, now
    )
    plan_node = make_plan_node(traced_planner_call)
    collect_and_gate_node = make_collect_and_gate_node(fetch_find_products_batch, now)
    explain_node = make_explain_node(traced_explainer_call)

    _add_node(graph, "read", read_node)
    _add_node(graph, "diagnose", diagnose_node)
    _add_node(graph, "compare_channels", compare_channels_node)
    _add_node(graph, "plan", plan_node)
    _add_node(graph, "collect_and_gate", collect_and_gate_node)
    _add_node(graph, "rank", rank_node)
    _add_node(graph, "explain", explain_node)

    graph.set_entry_point("read")
    graph.add_conditional_edges(
        "read", _continue_or_end, {"end": END, "continue": "diagnose"}
    )
    graph.add_conditional_edges(
        "diagnose", _continue_or_end, {"end": END, "continue": "compare_channels"}
    )
    graph.add_edge("compare_channels", "plan")
    graph.add_conditional_edges(
        "plan", _continue_or_end, {"end": END, "continue": "collect_and_gate"}
    )
    graph.add_conditional_edges(
        "collect_and_gate", _continue_or_end, {"end": END, "continue": "rank"}
    )
    graph.add_edge("rank", "explain")
    graph.add_edge("explain", END)

    return graph.compile(checkpointer=checkpointer)
