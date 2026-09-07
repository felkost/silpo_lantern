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
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.lantern.domain.models import ConsentRecord, Receipt
from src.lantern.graph.nodes import (
    make_collect_and_gate_node,
    make_compare_channels_node,
    make_diagnose_node,
    make_explain_node,
    make_persist_receipt_node,
    make_plan_node,
    make_read_node,
    make_write_and_readback_node,
    make_write_guard_node,
    rank_node,
)
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.graph.state import RecoveryState
from src.lantern.memory.repository import IdempotencyState
from src.lantern.observability.tracer import (
    redact_explainer_input,
    redact_planner_input,
    redact_write_input,
    redact_write_output,
    traced_llm_call,
)
from src.lantern.policies.loader import DEFAULT_REGISTRY_PATH, PolicyRegistry


def _unconfigured_load_consent(action_id: str) -> Tuple[Optional[ConsentRecord], bool]:
    raise NotImplementedError(
        "build_recovery_graph: load_consent not configured — the write path"
        " cannot run without it (it is unreachable offline without a"
        " checkpointer + resume, so a test that never reaches write_guard"
        " never calls this)."
    )


def _unconfigured_call_write_tool(
    tool_name: str, args: Dict[str, Any]
) -> Dict[str, Any]:
    raise NotImplementedError("build_recovery_graph: call_write_tool not configured")


def _unconfigured_claim_and_consume(
    owner: str, cart_id: str, action_id: str, args_hash: str
) -> Tuple[bool, IdempotencyState]:
    raise NotImplementedError("build_recovery_graph: claim_and_consume not configured")


def _unconfigured_mark_action(
    owner: str, cart_id: str, action_id: str, state: IdempotencyState
) -> None:
    raise NotImplementedError("build_recovery_graph: mark_action not configured")


def _unconfigured_save_receipt(receipt: Receipt) -> None:
    raise NotImplementedError("build_recovery_graph: save_receipt not configured")


def _unconfigured_tool_schema_hashes(tool_name: str) -> Tuple[str, str, bool]:
    raise NotImplementedError("build_recovery_graph: tool_schema_hashes not configured")


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
    """The one routing rule shared by every fail-safe exit point before
    the write segment: a node that reached a terminal status ends the graph
    immediately; anything else continues to the next step.

    `no_action_available` is terminal but not a failure -- the cart is
    simply blocked by something no proposal here can clear. It ends the
    graph for the same reason `aborted` does: every node after this point
    exists to build, authorize or perform a write.
    """
    terminal = ("aborted", "no_action_available")
    return "end" if state["status"] in terminal else "continue"


def _another_round_or_end(state: RecoveryState) -> str:
    """`persist_receipt_node` signals a further round by clearing the spent
    consent and returning the state to `diagnosed`; anything terminal ends
    the graph.
    """
    return "retry" if state["status"] == "diagnosed" else "end"


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
    load_consent: Callable[
        [str], Tuple[Optional[ConsentRecord], bool]
    ] = _unconfigured_load_consent,
    call_write_tool: Callable[
        [str, Dict[str, Any]], Dict[str, Any]
    ] = _unconfigured_call_write_tool,
    claim_and_consume: Callable[
        [str, str, str, str], Tuple[bool, IdempotencyState]
    ] = _unconfigured_claim_and_consume,
    mark_action: Callable[
        [str, str, str, IdempotencyState], None
    ] = _unconfigured_mark_action,
    save_receipt: Callable[[Receipt], None] = _unconfigured_save_receipt,
    tool_schema_hashes: Callable[
        [str], Tuple[str, str, bool]
    ] = _unconfigured_tool_schema_hashes,
) -> "CompiledStateGraph[RecoveryState, Any, RecoveryState, RecoveryState]":
    """Builds the compiled graph: read -> diagnose -> compare_channels ->
    plan -> collect_and_gate -> rank -> explain -> write_guard ->
    write_and_readback -> persist_receipt -> END, with an
    `interrupt_before=["write_guard"]` pause for the guest's consent.
    `compare_channels` never aborts by itself (a cart with no coordinates,
    or a channel with no valid slots, degrades that one channel/the whole
    comparison rather than the recovery) — every other pre-consent step
    can abort on a `CartShapeError` or a missing precondition.

    **Without a checkpointer** (every offline unit test, and the
    read-path-only live scripts), `interrupt_before` has nothing to persist
    a pause against — measured directly (`.venv` probe): `graph.invoke(...)`
    simply returns the state as it stood right before the interrupted node,
    with no error and no partial execution of it. This is exactly why
    `explain`'s own `status="awaiting_consent"` is still what every G4-era
    test observes: `write_guard` is *reachable* in the topology but never
    *entered* without a real checkpointer to resume from, so the five new
    write-path parameters above default to stubs that raise if actually
    called — a caller that never configures them can still build and run
    the read path exactly as before.

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
    # D-G5-13: the write gets a span of its own, through the same wrapper.
    # Without this the one call that changes a guest's cart was the only
    # step in the graph leaving no trace at all -- found by the pre-merge
    # audit, after the live runs had already happened.
    traced_call_write_tool = traced_llm_call(
        "write",
        call_write_tool,
        redact_write_input,
        version_tuple,
        trace_tags,
        process_outputs=redact_write_output,
    )

    read_node = make_read_node(fetch_my_cart, fetch_cart_by_id)
    diagnose_node = make_diagnose_node(registry)
    compare_channels_node = make_compare_channels_node(
        fetch_delivery_types, fetch_time_slots, fetch_find_products_batch, now
    )
    plan_node = make_plan_node(traced_planner_call)
    collect_and_gate_node = make_collect_and_gate_node(fetch_find_products_batch, now)
    explain_node = make_explain_node(traced_explainer_call)
    write_guard_node = make_write_guard_node(
        load_consent, fetch_my_cart, fetch_cart_by_id, tool_schema_hashes, now
    )
    write_and_readback_node = make_write_and_readback_node(
        traced_call_write_tool, fetch_cart_by_id, claim_and_consume, mark_action, now
    )
    persist_receipt_node = make_persist_receipt_node(save_receipt)

    _add_node(graph, "read", read_node)
    _add_node(graph, "diagnose", diagnose_node)
    _add_node(graph, "compare_channels", compare_channels_node)
    _add_node(graph, "plan", plan_node)
    _add_node(graph, "collect_and_gate", collect_and_gate_node)
    _add_node(graph, "rank", rank_node)
    _add_node(graph, "explain", explain_node)
    _add_node(graph, "write_guard", write_guard_node)
    _add_node(graph, "write_and_readback", write_and_readback_node)
    _add_node(graph, "persist_receipt", persist_receipt_node)

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
    # Conditional, not a plain edge: without this an `explain` that found
    # nothing to offer would still travel to `write_guard` and park on its
    # `interrupt_before` pause, leaving a session waiting for consent to an
    # empty list -- and the next `/events` call would resume into a guard
    # refusal instead of simply having ended.
    graph.add_conditional_edges(
        "explain", _continue_or_end, {"end": END, "continue": "write_guard"}
    )
    graph.add_conditional_edges(
        "write_guard", _continue_or_end, {"end": END, "continue": "write_and_readback"}
    )
    graph.add_edge("write_and_readback", "persist_receipt")
    # The write path can loop back for a second consent+write round when
    # the receipt shows the blocker survived a correct write -- see
    # `persist_receipt_node`, which is the only thing that decides it.
    # `interrupt_before=["write_guard"]` still applies on every pass, so a
    # further write is impossible without a further consent.
    graph.add_conditional_edges(
        "persist_receipt", _another_round_or_end, {"end": END, "retry": "diagnose"}
    )

    # D-G5-08: static interrupt before the ONLY node that may authorize a
    # write (CLAUDE.md section 4). Measured (.venv probe): with no
    # checkpointer this has no effect on `invoke` beyond stopping before
    # `write_guard` runs — see this function's own docstring.
    return graph.compile(checkpointer=checkpointer, interrupt_before=["write_guard"])
