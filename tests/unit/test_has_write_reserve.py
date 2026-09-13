"""the brief's pre-write reserve check -- 20s and two
reads must remain before a write may begin.
"""

from datetime import datetime, timedelta, timezone

from src.lantern.graph.state import (
    MAX_MCP_ATTEMPTS,
    has_write_reserve,
    new_recovery_state,
)

_NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)


def test_fresh_state_has_reserve() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_NOW)
    assert has_write_reserve(state, _NOW) is True


def test_deadline_too_close_has_no_reserve() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_NOW)
    almost_at_deadline = state["deadline"] - timedelta(seconds=5)
    assert has_write_reserve(state, almost_at_deadline) is False


def test_mcp_attempts_near_the_ceiling_has_no_reserve() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_NOW)
    near_ceiling = MAX_MCP_ATTEMPTS - 1
    state = {**state, "mcp_attempts_used": near_ceiling}  # type: ignore[typeddict-item]
    assert has_write_reserve(state, _NOW) is False
