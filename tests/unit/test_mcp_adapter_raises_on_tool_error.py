"""`CallToolResult.isError` is a field the
caller must check — measured, the SDK does not raise for it. A naive caller
could treat an `isError: true` payload as ordinary data. The typed adapter
must raise instead, carrying the result's `content` for diagnostics.
"""

import pytest
from mcp import types as mcp_types

from src.lantern.mcp.errors import McpToolExecutionError
from src.lantern.mcp.client import raise_on_tool_error


def test_passes_through_a_successful_result() -> None:
    result = mcp_types.CallToolResult(content=[], isError=False)
    assert raise_on_tool_error(result) is result


def test_raises_typed_error_when_is_error_true() -> None:
    content = [mcp_types.TextContent(type="text", text="cart not found")]
    result = mcp_types.CallToolResult(content=content, isError=True)
    with pytest.raises(McpToolExecutionError) as exc_info:
        raise_on_tool_error(result)
    assert exc_info.value.content == content
