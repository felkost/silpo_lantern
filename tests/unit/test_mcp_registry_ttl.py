"""The MCP registry's wall-clock TTL is an
addition beyond the event-driven invalidation list, not a
restatement of it. Uses an injectable clock so the test is deterministic:
if a fixture needs a timestamp, inject it.
"""

from typing import Any, Dict, List

from src.lantern.mcp.client import ToolRegistry


def _list_tools_raw(*names: str) -> List[Dict[str, Any]]:
    return [{"name": name, "inputSchema": {"type": "object"}} for name in names]


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_returns_cached_result_within_ttl() -> None:
    calls = []

    def fetch() -> list:
        calls.append(1)
        return _list_tools_raw("tool_a")

    clock = _FakeClock()
    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=clock)

    registry.get()
    registry.get()

    assert len(calls) == 1


def test_refetches_after_ttl_expires() -> None:
    calls = []

    def fetch() -> list:
        calls.append(1)
        return _list_tools_raw("tool_a")

    clock = _FakeClock()
    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=clock)

    registry.get()
    clock.advance(901)
    registry.get()

    assert len(calls) == 2


def test_force_refresh_ignores_ttl() -> None:
    calls = []

    def fetch() -> list:
        calls.append(1)
        return _list_tools_raw("tool_a")

    clock = _FakeClock()
    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=clock)

    registry.get()
    registry.get(force_refresh=True)

    assert len(calls) == 2


def test_invalidate_forces_next_get_to_refetch() -> None:
    calls = []

    def fetch() -> list:
        calls.append(1)
        return _list_tools_raw("tool_a")

    clock = _FakeClock()
    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=clock)

    registry.get()
    registry.invalidate()
    registry.get()

    assert len(calls) == 2
