"""G9 (D78): the 18-repeat runner must trace the way the production graph
traces, or its 63 live LLM calls leave the one artefact section 13.4 asks
for -- a trace per run -- either absent or unusable.

`core_e2e_repeats.py` built bare `ChatOpenAI` callables and handed them
straight to `replay()`. LangGraph's own auto-instrumentation still emitted
runs (`LANGSMITH_TRACING=true` is set in the author's environment), so the
traces LOOKED fine in the UI while missing everything that makes them
reviewable:

* no `install_trace_redaction()`, so `strip_coordinates` was never primed
  on the process-wide cached client -- the exact 2026-09-07 measured leak
  the tracer's own docstring records, where LangGraph serialises the whole
  `RecoveryState` into a neighbouring span. The repeats happened to run
  against fixtures whose coordinates are synthetic or null, so nothing
  real left the process; that is the fixture's doing, not the runner's.
* no `traced_llm_call` wrapper, so no named `planner`/`explainer` span and
  no version-tuple metadata -- schema hash, prompt versions, model ids --
  on any of the 63 calls. A trace that cannot say which prompt version
  produced it cannot support a claim about the run.

Both are asserted here rather than eyeballed in the LangSmith UI, because
the UI is where they were missed twice.
"""

import inspect

import scripts.core_e2e_repeats as repeats


def test_the_runner_installs_trace_redaction() -> None:
    source = inspect.getsource(repeats)
    assert "install_trace_redaction()" in source, (
        "the repeats runner makes live LLM calls without priming the "
        "redaction hook on LangSmith's cached client"
    )


def test_the_live_callables_are_wrapped_in_the_project_spans() -> None:
    source = inspect.getsource(repeats._live_callables)
    assert "traced_llm_call" in source, (
        "planner/explainer are called raw -- no named span, no version "
        "tuple, nothing tying a trace to a prompt version"
    )


def test_every_run_row_records_its_thread_id() -> None:
    """A result row that cannot be matched to a trace is a number with no
    evidence behind it."""
    source = inspect.getsource(repeats)
    assert "thread_id" in source, "run rows carry no handle back to a trace"
