"""Redaction before every send to LangSmith. An MCP error's `.data` is
dropped entirely — attacker/server-controlled free-form content with no
legitimate reason to reach a third-party trace — and `.message` is
scrubbed too, since it turned out to be exactly as untrusted as `.data`,
not merely shorter.
"""

from typing import Dict, Union

from scripts.secret_scan import PATTERNS

from src.lantern.mcp.errors import McpProtocolError

_MAX_MESSAGE_LENGTH = 500
_REDACTED_MESSAGE = "[redacted: message matched a credential-shaped pattern]"


def sanitize_mcp_error_for_trace(error: McpProtocolError) -> Dict[str, Union[int, str]]:
    """Reduces an MCP protocol error to the only fields safe to trace.
    `.data` is never included, regardless of its shape. `.message` is
    redacted wholesale if it matches a known credential shape (reusing
    `scripts/secret_scan.py`'s own patterns — the same threat, same rules)
    and truncated regardless, since an unbounded message is itself an
    injection surface.

    This covers credential-shaped leakage; broader free-text PII in
    `.message` is not fully addressed here — no real captured payload
    exists yet to build a complete rule set against.
    """
    message = error.message
    if any(pattern.search(message) for pattern in PATTERNS.values()):
        message = _REDACTED_MESSAGE
    elif len(message) > _MAX_MESSAGE_LENGTH:
        message = message[:_MAX_MESSAGE_LENGTH] + "...[truncated]"
    return {"code": error.code, "message": message}
