"""The MCP server is treated as untrusted. An oversized or excessively
verbose `tools/list` response must be rejected before the registry spends
work canonicalizing/hashing/diffing it, not after.
"""

import pytest
from typing import Any, Dict, List

from src.lantern.mcp.client import ToolRegistry
from src.lantern.mcp.errors import McpResponseTooLargeError


def _list_tools_raw(count: int, description_size: int = 10) -> List[Dict[str, Any]]:
    return [
        {
            "name": f"tool_{i}",
            "description": "x" * description_size,
            "inputSchema": {"type": "object"},
        }
        for i in range(count)
    ]


def test_a_normal_sized_response_is_accepted() -> None:
    registry = ToolRegistry(
        fetch=lambda: _list_tools_raw(40), ttl_seconds=900, now=lambda: 0.0
    )
    cached = registry.get()
    assert len(cached.result.tools) == 40


def test_a_response_with_too_many_tools_is_rejected() -> None:
    registry = ToolRegistry(
        fetch=lambda: _list_tools_raw(10_000), ttl_seconds=900, now=lambda: 0.0
    )
    with pytest.raises(McpResponseTooLargeError):
        registry.get()


def test_a_response_over_the_byte_size_ceiling_is_rejected() -> None:
    registry = ToolRegistry(
        fetch=lambda: _list_tools_raw(50, description_size=1_000_000),
        ttl_seconds=900,
        now=lambda: 0.0,
    )
    with pytest.raises(McpResponseTooLargeError):
        registry.get()


def test_rejecting_an_oversized_response_does_not_update_the_cache() -> None:
    responses = [_list_tools_raw(10_000), _list_tools_raw(5)]

    def fetch() -> list:
        return responses.pop(0)

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    with pytest.raises(McpResponseTooLargeError):
        registry.get()
    # a subsequent, well-behaved fetch must not be blocked by leftover state
    cached = registry.get(force_refresh=True)
    assert len(cached.result.tools) == 5
