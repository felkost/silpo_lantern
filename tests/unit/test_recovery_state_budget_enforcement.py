"""The budget envelope ("до 12 циклів агента, 30
спроб MCP, 60 000 сумарних вхідних/вихідних токенів і 90 с активного
виконання на сегмент") existed only as a test name before this —
no counter field, no enforcement function anywhere. This is
what makes it a real mechanism: `RecoveryState` carries the counters,
`enforce_budget` is the single function every budget-consuming node calls
after doing its work, and exhausting any one dimension transitions to
`status="aborted"` with a reason, never an unbounded retry.
"""

from datetime import datetime, timedelta, timezone

from src.lantern.graph.state import (
    MAX_CYCLES,
    MAX_MCP_ATTEMPTS,
    MAX_TOKENS,
    enforce_budget,
    new_recovery_state,
)


def _now() -> datetime:
    return datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def test_a_fresh_state_is_within_budget() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    checked = enforce_budget(state, now=_now())
    assert checked["status"] == "reading"
    assert checked["error"] is None


def test_exceeding_cycles_aborts_with_a_reason() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["cycles_used"] = MAX_CYCLES + 1

    checked = enforce_budget(state, now=_now())

    assert checked["status"] == "aborted"
    assert checked["error"] is not None
    assert "cycles_used" in checked["error"]


def test_exceeding_mcp_attempts_aborts_with_a_reason() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["mcp_attempts_used"] = MAX_MCP_ATTEMPTS + 1

    checked = enforce_budget(state, now=_now())

    assert checked["status"] == "aborted"
    assert "mcp_attempts_used" in checked["error"]


def test_exceeding_tokens_aborts_with_a_reason() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["tokens_used"] = MAX_TOKENS + 1

    checked = enforce_budget(state, now=_now())

    assert checked["status"] == "aborted"
    assert "tokens_used" in checked["error"]


def test_passing_the_deadline_aborts_with_a_reason() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())

    checked = enforce_budget(state, now=state["deadline"] + timedelta(seconds=1))

    assert checked["status"] == "aborted"
    assert "deadline" in checked["error"]


def test_exactly_at_the_ceiling_is_still_within_budget() -> None:
    """Boundary check: "до 12 циклів" (up to 12) —
    the ceiling itself is allowed, only exceeding it aborts."""
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["cycles_used"] = MAX_CYCLES
    state["mcp_attempts_used"] = MAX_MCP_ATTEMPTS
    state["tokens_used"] = MAX_TOKENS

    checked = enforce_budget(state, now=state["deadline"])

    assert checked["status"] != "aborted"


def test_multiple_exhausted_dimensions_are_all_named_in_the_reason() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["cycles_used"] = MAX_CYCLES + 1
    state["tokens_used"] = MAX_TOKENS + 1

    checked = enforce_budget(state, now=_now())

    assert "cycles_used" in checked["error"]
    assert "tokens_used" in checked["error"]


def test_enforce_budget_does_not_mutate_the_input_state() -> None:
    """`RecoveryState` is a TypedDict — a plain, mutable dict at runtime.
    A function that silently mutates its input instead of returning a new
    state is exactly the kind of thing that makes a LangGraph node's
    behavior depend on call order rather than on its own return value."""
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["cycles_used"] = MAX_CYCLES + 1
    original_status = state["status"]

    enforce_budget(state, now=_now())

    assert state["status"] == original_status


def test_an_already_aborted_state_stays_aborted_even_if_counters_look_fine() -> None:
    """Budget enforcement never revives a state some other check already
    aborted for a different reason (e.g. a CartShapeError from the read
    node) — `enforce_budget` only ever adds a reason, never clears one."""
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["status"] = "aborted"
    state["error"] = "CartShapeError: missing shipments"

    checked = enforce_budget(state, now=_now())

    assert checked["status"] == "aborted"
    assert checked["error"] == "CartShapeError: missing shipments"
