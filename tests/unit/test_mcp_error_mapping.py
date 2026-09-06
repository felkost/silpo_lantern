"""Plan section 9.1's "typed errors" strengthening, measured to have zero
donor precedent: the donor's silpo_mcp.py
never touches `McpError`/`ErrorData`/JSON-RPC codes at all. This is new code.
An unrecognized JSON-RPC error code must still map to a typed exception, never
crash the mapping itself or get silently swallowed (same fail-safe philosophy
as DR-06 for unknown validation codes).
"""

from mcp import types as mcp_types
from mcp.shared.exceptions import McpError

from src.lantern.mcp.errors import McpProtocolError, map_mcp_error


def _mcp_error(code: int, message: str) -> McpError:
    return McpError(mcp_types.ErrorData(code=code, message=message))


def test_maps_a_known_json_rpc_error_code() -> None:
    mapped = map_mcp_error(_mcp_error(mcp_types.METHOD_NOT_FOUND, "no such tool"))
    assert isinstance(mapped, McpProtocolError)
    assert mapped.code == mcp_types.METHOD_NOT_FOUND
    assert mapped.message == "no such tool"


def test_maps_invalid_params_too() -> None:
    mapped = map_mcp_error(_mcp_error(mcp_types.INVALID_PARAMS, "bad args"))
    assert isinstance(mapped, McpProtocolError)
    assert mapped.code == mcp_types.INVALID_PARAMS


def test_unknown_error_code_still_maps_without_crashing() -> None:
    """Fail-safe: a code this project has never seen must not raise from
    inside the mapper itself, and must not be dropped silently.
    """
    mapped = map_mcp_error(_mcp_error(-32099, "some code nobody registered"))
    assert isinstance(mapped, McpProtocolError)
    assert mapped.code == -32099
    assert mapped.message == "some code nobody registered"
