"""One sync `call_tool` facade over the SDK's async client -- the piece
`client.py` (the registry) and `auth.py` (OAuth storage) don't provide.
Before this module, every live MCP call in the project was a duplicated
copy of this same async/sync bridge inside `scripts/capture_fixture.py`,
`scripts/g4_live_evidence_gate_run.py`, and `scripts/silpo_mcp_login.py`.
G5+G6 (D-G5-10): this is the module the write call goes through, so D20's
recursive `BaseExceptionGroup` unwrap -- measured necessary on a read --
cannot silently fail to apply to a write.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from mcp.client.auth.oauth2 import OAuthClientProvider
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientMetadata
from pydantic import AnyUrl

from src.lantern.mcp.auth import (
    DiskTokenStorage,
    build_redirect_handler,
    callback_handler,
)
from src.lantern.mcp.client import raise_on_tool_error

DEFAULT_MCP_URL = "https://mcp.silpo.ua/mcp"


async def _call_tool_async(
    tool_name: str, arguments: Dict[str, Any], server_url: str
) -> Dict[str, Any]:
    storage = DiskTokenStorage()
    auth = OAuthClientProvider(
        server_url=server_url,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[AnyUrl("https://localhost/callback")],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=build_redirect_handler(storage),
        callback_handler=callback_handler,
    )
    async with streamablehttp_client(server_url, auth=auth) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            raise_on_tool_error(result)
            return result.structuredContent or {}


def call_tool(
    tool_name: str, arguments: Dict[str, Any], *, server_url: str = DEFAULT_MCP_URL
) -> Dict[str, Any]:
    """Bridges one async MCP tool call into the sync `Callable` shape the
    graph nodes expect. `asyncio.run` wraps any exception raised inside
    the SDK's own `anyio` task groups (the streamable-HTTP transport, then
    separately the session's own teardown) in a `BaseExceptionGroup` --
    measured **two layers deep** for this transport (D20) -- so a plain
    `except McpAdapterError` at the call site would never see the real
    exception without this unwrap.
    """
    try:
        return asyncio.run(_call_tool_async(tool_name, arguments, server_url))
    except* Exception as eg:
        cause: BaseException = eg
        while isinstance(cause, BaseExceptionGroup) and len(cause.exceptions) == 1:
            cause = cause.exceptions[0]
        raise cause from None
