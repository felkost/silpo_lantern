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

from src.lantern.domain.models import ActionProposal

T = TypeVar("T")


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


def traced_llm_call(
    name: str,
    fn: Callable[..., T],
    process_inputs: Callable[[Mapping[str, Any]], Dict[str, Any]],
    version_tuple: Optional[Mapping[str, str]] = None,
    tags: Optional[Sequence[str]] = None,
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
    traced = traceable(name=name, process_inputs=process_inputs)(fn)
    metadata = dict(version_tuple) if version_tuple else {}

    def call(*args: Any, **kwargs: Any) -> T:
        extra = LangSmithExtra(metadata=metadata, tags=list(tags) if tags else None)
        return traced(*args, langsmith_extra=extra, **kwargs)

    return call
