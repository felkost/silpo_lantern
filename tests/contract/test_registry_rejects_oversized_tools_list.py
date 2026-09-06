"""F11 (docs/g1-g2-stage-spec.md): the MCP server is this project's own
stated untrusted threat model (CLAUDE.md section 4). An oversized or
excessively verbose `tools/list` response must be rejected before the
registry spends work canonicalizing/hashing/diffing it, not after.
"""

import pytest
from mcp import types as mcp_types

from src.lantern.mcp.client import ToolRegistry
from src.lantern.mcp.errors import McpResponseTooLargeError


def _list_tools_result(
    count: int, description_size: int = 10
) -> mcp_types.ListToolsResult:
    return mcp_types.ListToolsResult(
        tools=[
            mcp_types.Tool(
                name=f"tool_{i}",
                description="x" * description_size,
                inputSchema={"type": "object"},
            )
            for i in range(count)
        ]
    )


def test_a_normal_sized_response_is_accepted() -> None:
    registry = ToolRegistry(
        fetch=lambda: _list_tools_result(40), ttl_seconds=900, now=lambda: 0.0
    )
    cached = registry.get()
    assert len(cached.result.tools) == 40


def test_a_response_with_too_many_tools_is_rejected() -> None:
    registry = ToolRegistry(
        fetch=lambda: _list_tools_result(10_000), ttl_seconds=900, now=lambda: 0.0
    )
    with pytest.raises(McpResponseTooLargeError):
        registry.get()


def test_a_response_over_the_byte_size_ceiling_is_rejected() -> None:
    registry = ToolRegistry(
        fetch=lambda: _list_tools_result(50, description_size=1_000_000),
        ttl_seconds=900,
        now=lambda: 0.0,
    )
    with pytest.raises(McpResponseTooLargeError):
        registry.get()


def test_rejecting_an_oversized_response_does_not_update_the_cache() -> None:
    responses = [_list_tools_result(10_000), _list_tools_result(5)]

    def fetch() -> mcp_types.ListToolsResult:
        return responses.pop(0)

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    with pytest.raises(McpResponseTooLargeError):
        registry.get()
    # a subsequent, well-behaved fetch must not be blocked by leftover state
    cached = registry.get(force_refresh=True)
    assert len(cached.result.tools) == 5
