"""F12 (widened in round 2): a JSON-RPC error's
`.data` field is attacker/server-controlled free-form content and must never
reach a LangSmith trace verbatim — dropped entirely, not merely truncated.
Round 2 found `.message` is exactly as untrusted as `.data`; the first draft
only scrubbed `.data`. Both must be handled before anything reaches
`observability/`.
"""

from src.lantern.mcp.errors import McpProtocolError
from src.lantern.observability.redaction import sanitize_mcp_error_for_trace


def test_data_is_never_included_in_the_traced_representation() -> None:
    error = McpProtocolError(
        code=-32602, message="bad args", data={"secret": "leak-me"}
    )
    traced = sanitize_mcp_error_for_trace(error)
    assert "data" not in traced
    assert "leak-me" not in str(traced)


def test_a_short_ordinary_message_passes_through() -> None:
    error = McpProtocolError(code=-32601, message="no such tool")
    traced = sanitize_mcp_error_for_trace(error)
    assert traced == {"code": -32601, "message": "no such tool"}


def test_an_overlong_message_is_truncated() -> None:
    error = McpProtocolError(code=-32000, message="x" * 10_000)
    traced = sanitize_mcp_error_for_trace(error)
    assert len(traced["message"]) < 10_000


def test_a_message_carrying_a_credential_shaped_string_is_redacted() -> None:
    # Built at runtime, not written as a literal "key=value" in this file's
    # source text — the shape must still match scripts/secret_scan.py's own
    # pattern (this is exactly what the test proves), but a literal match in
    # the test source itself would trip that same scanner on a deliberately
    # fake fixture value.
    fake_value = "".join(["fake", "credential", "-", "1234567890123"])
    error = McpProtocolError(
        code=-32000, message="upstream call failed: " + "api_key" + "=" + fake_value
    )
    traced = sanitize_mcp_error_for_trace(error)
    assert fake_value not in traced["message"]
