"""A TTL-only cache can serve a stale schema for up to the TTL window even
if the server just changed it mid-session. The
registry must invalidate immediately on a `McpProtocolError` carrying
`METHOD_NOT_FOUND`/`INVALID_PARAMS`, or a `McpSchemaError` (a cached
`inputSchema` failed to validate a call's arguments) — not wait for the TTL.
"""

from typing import Any, Dict, List

from mcp import types as mcp_types

from src.lantern.mcp.client import ToolRegistry
from src.lantern.mcp.errors import McpProtocolError, McpSchemaError


def _list_tools_raw(*names: str) -> List[Dict[str, Any]]:
    return [{"name": name, "inputSchema": {"type": "object"}} for name in names]


def test_method_not_found_invalidates_the_cache_immediately() -> None:
    calls = []

    def fetch() -> list:
        calls.append(1)
        return _list_tools_raw("a")

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    registry.get()

    registry.observe_error(
        McpProtocolError(code=mcp_types.METHOD_NOT_FOUND, message="x")
    )
    registry.get()

    assert len(calls) == 2


def test_invalid_params_invalidates_the_cache_immediately() -> None:
    calls = []

    def fetch() -> list:
        calls.append(1)
        return _list_tools_raw("a")

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    registry.get()

    registry.observe_error(McpProtocolError(code=mcp_types.INVALID_PARAMS, message="x"))
    registry.get()

    assert len(calls) == 2


def test_schema_error_invalidates_the_cache_immediately() -> None:
    calls = []

    def fetch() -> list:
        calls.append(1)
        return _list_tools_raw("a")

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    registry.get()

    registry.observe_error(
        McpSchemaError("cached inputSchema rejected these arguments")
    )
    registry.get()

    assert len(calls) == 2


def test_an_unrelated_protocol_error_code_does_not_invalidate() -> None:
    """Only the two named codes (and schema errors) force invalidation —
    an unrelated protocol error is not itself evidence the cached schema is
    stale.
    """
    calls = []

    def fetch() -> list:
        calls.append(1)
        return _list_tools_raw("a")

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    registry.get()

    registry.observe_error(McpProtocolError(code=-32000, message="internal error"))
    registry.get()

    assert len(calls) == 1
