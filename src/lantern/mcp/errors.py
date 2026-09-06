"""Typed error hierarchy for the MCP adapter — the donor's `silpo_mcp.py`
never touched `McpError` or JSON-RPC codes at all.
"""

from typing import Optional

from mcp.shared.exceptions import McpError


class McpAdapterError(Exception):
    """Base of every typed error this adapter raises."""


class McpTransportError(McpAdapterError):
    """A connection-level failure (network, timeout) — not a JSON-RPC error."""


class McpProtocolError(McpAdapterError):
    """A JSON-RPC-level error (`ErrorData`). An unrecognized `.code` still
    produces one of these rather than crashing the mapper or being silently
    dropped — the same fail-safe philosophy applies to unknown validation
    codes.
    """

    def __init__(self, code: int, message: str, data: Optional[object] = None):
        super().__init__(f"MCP protocol error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class McpToolExecutionError(McpAdapterError):
    """Raised whenever a `CallToolResult.isError` is `True` — a JSON-RPC-level
    success can still carry a tool-level failure; callers never see a raw
    `CallToolResult` with `isError=True` treated as success.
    """

    def __init__(self, content: object):
        super().__init__(f"tool call failed: {content!r}")
        self.content = content


class McpSchemaError(McpAdapterError):
    """A cached `inputSchema` failed to validate a call's arguments —
    triggers registry invalidation.
    """


class McpResponseTooLargeError(McpAdapterError):
    """A `tools/list` response exceeded the registry's size/count ceiling —
    rejected before any hashing/diffing work is spent on it. Not a
    JSON-RPC-level error, so distinct from `McpProtocolError`.
    """


class McpAuthExpiredError(McpAdapterError):
    """A previously-valid `DiskTokenStorage` token is now rejected — distinct
    from `SilpoMcpAuthRequiredError` (never logged in at all) so a mid-demo
    expiry surfaces clearly rather than as an opaque transport failure.
    """


def map_mcp_error(exc: McpError) -> McpProtocolError:
    """Translate the SDK's `McpError` into this project's typed hierarchy.
    Never raises on an unrecognized code — see `McpProtocolError`'s own
    fail-safe contract.
    """
    return McpProtocolError(
        code=exc.error.code, message=exc.error.message, data=exc.error.data
    )
