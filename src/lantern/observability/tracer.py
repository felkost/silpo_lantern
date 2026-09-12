"""LangSmith tracer wrapper: wraps the two LLM call points (`planner_call`,
`explainer_call`) with a named traced span carrying the version tuple —
server/release/schema hash and app/prompt/policy/model versions — so it
appears in the trace.

Two facts measured directly against the installed SDK (`langsmith==0.12.2`),
not assumed from documentation:

1. `traceable`'s `process_inputs`/`process_outputs` hooks — this module's
   redaction mechanism — are called ONLY when tracing is actually active
   (`LANGSMITH_TRACING=true` plus an API key). With no env vars set, they
   are never invoked at all. This project's offline gate never enables
   tracing, so this module's own test suite exercises the redaction
   FUNCTIONS directly as plain functions, never by enabling live tracing —
   which was also measured to attempt a real outbound HTTPS POST to
   `api.smith.langchain.com` even with a bogus key (rejected 403, not a
   local no-op). Never set `LANGSMITH_TRACING=true` inside an automated
   test.
2. `process_inputs` receives a dict keyed by the wrapped function's
   parameter name (e.g. `{"state": <value>}` for a one-positional-arg
   function), not a positional tuple.
"""

from typing import Any, Callable, Dict, Mapping, Optional, Sequence, TypeVar

from langsmith import traceable
from langsmith.run_helpers import LangSmithExtra
from langsmith.run_trees import get_cached_client

from src.lantern.domain.models import ActionProposal

T = TypeVar("T")


# Address-adjacent fields, stripped from EVERY payload before it leaves the
# process -- not just from the spans this module wraps.
COORDINATE_KEYS = frozenset({"latitude", "longitude"})


def strip_coordinates(payload: Any) -> Any:
    """Recursively removes the cart's coordinates from anything on its way
    to LangSmith.

    `redact_planner_input` already drops them from its own span, on the
    stated grounds that address-adjacent data has no legitimate reason to
    reach a third-party trace. That was only ever true of the three spans
    this module wraps: LangGraph instruments every node itself and
    serialises the whole `RecoveryState`, so a real exported trace carried
    `latitude`/`longitude` verbatim in a neighbouring span -- measured on a
    live run, 2026-09-07.
    """
    if isinstance(payload, Mapping):
        return {
            key: strip_coordinates(value)
            for key, value in payload.items()
            if key not in COORDINATE_KEYS
        }
    if isinstance(payload, list):
        return [strip_coordinates(item) for item in payload]
    return payload


def install_trace_redaction() -> None:
    """Primes LangSmith's process-wide cached client with the redaction
    hook, so it applies to spans this project never created.

    Must run before anything else touches the client: `get_cached_client`
    builds it on first call and ignores the arguments of every call after
    that. Rather than trust ordering, this verifies the hook actually
    landed and raises if it did not -- a redactor that silently failed to
    install is worse than none, because the trace looks supervised.
    """
    client = get_cached_client(
        hide_inputs=strip_coordinates, hide_outputs=strip_coordinates
    )
    installed = getattr(client, "_hide_inputs", None) is strip_coordinates
    if not installed:
        raise RuntimeError(
            "LangSmith's cached client already existed, so trace redaction was "
            "not installed. Call install_trace_redaction() before anything "
            "creates a client or emits a span."
        )


def redact_planner_input(kwargs: Mapping[str, Any]) -> Dict[str, Any]:
    """What the planner call actually traces: never the cart's raw
    coordinates — address-adjacent data has no legitimate reason to reach a
    third-party trace — never the full raw diagnosis/disclosure payload —
    only a summary a trace reviewer needs to understand what the planner
    was asked.
    """
    state = kwargs.get("state")
    if state is None:
        return dict(kwargs)
    diagnosis = state.get("diagnosis")
    return {
        "session_id": state.get("session_id"),
        "trace_id": state.get("trace_id"),
        "primary_code": diagnosis.primary_code if diagnosis else None,
        "gap": (
            str(diagnosis.gap) if diagnosis and diagnosis.gap is not None else None
        ),
        "channel_count": len(state.get("channel_comparison", [])),
    }


def redact_explainer_input(kwargs: Mapping[str, Any]) -> Dict[str, Any]:
    """Traces only the fields the guest will actually see reflected in the
    explainer's own sentence — never `evidence`'s `source_tool`/
    `captured_at`, which are audit-only and add nothing a trace reviewer
    needs repeated."""
    proposal = kwargs.get("proposal")
    if not isinstance(proposal, ActionProposal):
        return dict(kwargs)
    return {
        "action_id": proposal.action_id,
        "product_name": proposal.product_name,
        "quantity": str(proposal.quantity),
        "expected_delta": str(proposal.expected_delta),
    }


def redact_write_input(kwargs: Mapping[str, Any]) -> Dict[str, Any]:
    """What the WRITE call traces. Every identifier in
    `canonical_args` is dropped: the cart id and the product ids identify a
    real person's real basket, and a third-party trace is exactly the place
    they must not appear. What a reviewer needs is that a write happened,
    against which tool, with how many lines and at what quantity -- the
    money and the identity are already in the receipt row, which stays in
    this project's own database.

    Deliberately not `dict(kwargs)` on the fallback path, unlike the two
    LLM redactors above: those summarise inputs that carry no identifiers
    worth hiding, while an unrecognised shape here would leak the raw
    arguments verbatim. An unexpected shape traces its own shape, nothing
    more.
    """
    args = kwargs.get("args")
    tool_name = kwargs.get("tool_name")
    if not isinstance(args, Mapping):
        return {"tool_name": tool_name, "args": "<unrecognised shape, not traced>"}

    products = args.get("products")
    lines = products if isinstance(products, list) else []
    return {
        "tool_name": tool_name,
        "product_count": len(lines),
        "quantities": [
            line.get("quantity") for line in lines if isinstance(line, Mapping)
        ],
        "add_quantity": [
            line.get("addQuantity") for line in lines if isinstance(line, Mapping)
        ],
    }


def redact_write_output(outputs: Any) -> Dict[str, Any]:
    """The write tool answers `{success, summary, products:[{productId,
    quantity}]}` -- and echoes back the real product id. Redacting only the
    INPUTS left that id reaching a third-party trace anyway, which a live
    run showed after `redact_write_input` was already in place: the span's
    inputs were clean and its outputs carried
    `1eee7135-...` verbatim.

    Same rule as the input side, for the same reason: `success` and the
    line count are what a reviewer needs, and the identity of what a real
    person bought is not.
    """
    if not isinstance(outputs, Mapping):
        return {"output": "<unrecognised shape, not traced>"}
    products = outputs.get("products")
    lines = products if isinstance(products, list) else []
    return {
        "success": outputs.get("success"),
        "summary": outputs.get("summary"),
        "product_count": len(lines),
        "quantities": [
            line.get("quantity") for line in lines if isinstance(line, Mapping)
        ],
    }


def traced_llm_call(
    name: str,
    fn: Callable[..., T],
    process_inputs: Callable[[Mapping[str, Any]], Dict[str, Any]],
    version_tuple: Optional[Mapping[str, str]] = None,
    tags: Optional[Sequence[str]] = None,
    process_outputs: Optional[Callable[[Any], Dict[str, Any]]] = None,
) -> Callable[..., T]:
    """Wraps `fn` (a `planner_call`/`explainer_call`) with a named
    LangSmith span. `version_tuple` — schema_hash, prompt_version,
    model_id, policy_version — is attached as run metadata on every call, so
    the trace carries the full version tuple. `tags` is a run-level filter
    the caller controls (e.g. a live-run script marking its own traces) —
    without it, a run is otherwise indistinguishable from any other in the
    LangSmith UI.
    A no-op wrapper when tracing is disabled (measured — see module
    docstring), so callers never need to branch on whether tracing is on.
    """
    if process_outputs is None:
        traced = traceable(name=name, process_inputs=process_inputs)(fn)
    else:
        traced = traceable(
            name=name,
            process_inputs=process_inputs,
            process_outputs=process_outputs,
        )(fn)
    metadata = dict(version_tuple) if version_tuple else {}

    def call(*args: Any, **kwargs: Any) -> T:
        extra = LangSmithExtra(metadata=metadata, tags=list(tags) if tags else None)
        return traced(*args, langsmith_extra=extra, **kwargs)

    return call
