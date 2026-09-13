"""One sync `call_tool` facade over the SDK's async client -- the piece
`client.py` (the registry) and `auth.py` (OAuth storage) don't provide.
Before this module, every live MCP call in the project was a duplicated
copy of this same async/sync bridge inside `scripts/capture_fixture.py`,
`scripts/g4_live_evidence_gate_run.py`, and `scripts/silpo_mcp_login.py`.
this is the module the write call goes through, so the
recursive `BaseExceptionGroup` unwrap -- measured necessary on a read --
cannot silently fail to apply to a write.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from mcp.client.auth.oauth2 import OAuthClientProvider
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientMetadata
from pydantic import AnyUrl

from src.lantern.mcp.auth import (
    DiskTokenStorage,
    TokenStorageLike,
    build_redirect_handler,
    callback_handler,
)
from src.lantern.mcp.client import raise_on_tool_error

DEFAULT_MCP_URL = "https://mcp.silpo.ua/mcp"


# The guest whose credential this call should use. Set per request by
# `apps/api` right before it drives the graph, and read here at call
# time -- so one shared, cached production graph serves every guest
# instead of being rebuilt per session.
#
# Measured, not assumed (an early probe): a `ContextVar` set in the async
# caller IS visible inside LangGraph's SYNC node functions, through both
# `ainvoke` and `astream`. Had it not propagated, the fallback would have
# been a per-session graph.
#
# Default `None` means "no guest bound" -> `DiskTokenStorage`, which is
# what every author-run script wants and what kept them working unchanged.
current_token_storage: ContextVar[Optional[TokenStorageLike]] = ContextVar(
    "current_token_storage", default=None
)


def _build_auth(server_url: str) -> OAuthClientProvider:
    storage = current_token_storage.get() or DiskTokenStorage()
    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[AnyUrl("https://localhost/callback")],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=build_redirect_handler(storage),
        callback_handler=callback_handler,
    )


async def _call_tool_async(
    tool_name: str, arguments: Dict[str, Any], server_url: str
) -> Dict[str, Any]:
    auth = _build_auth(server_url)
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


async def _list_tools_async(server_url: str) -> List[Dict[str, Any]]:
    """KNOWN LIMITATION, carried forward rather than silently assumed
    solved: the public SDK (`ClientSession.list_tools`) parses straight
    into typed `Tool` objects with no exposed hook for the raw JSON-RPC
    bytes underneath. `mcp.client.reviewed_tools.json`'s baseline was
    generated from a genuinely raw captured fixture, and an earlier decision already
    measured that a `Tool.model_validate(...).model_dump(...)` round-trip
    does not reproduce that raw JSON byte-for-byte (the SDK adds fields
    the wire payload never had). This function's `model_dump(...)` output
    is therefore internally consistent (a real schema change still moves
    the hash), but the ABSOLUTE hash value will not match the tracked
    fixture's historical baseline computed from raw capture bytes.
    Before this schema-drift check is meaningful against a live server,
    `reviewed_tools.json`'s baseline must be regenerated from a live
    capture through this exact code path — the first live live run's job,
    not solvable offline.
    """
    auth = _build_auth(server_url)
    async with streamablehttp_client(server_url, auth=auth) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                for tool in result.tools
            ]


def call_tool(
    tool_name: str, arguments: Dict[str, Any], *, server_url: str = DEFAULT_MCP_URL
) -> Dict[str, Any]:
    """Bridges one async MCP tool call into the sync `Callable` shape the
    graph nodes expect. `asyncio.run` wraps any exception raised inside
    the SDK's own `anyio` task groups (the streamable-HTTP transport, then
    separately the session's own teardown) in a `BaseExceptionGroup` --
    measured **two layers deep** for this transport -- so a plain
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


def list_tools_raw(*, server_url: str = DEFAULT_MCP_URL) -> List[Dict[str, Any]]:
    """Sync `tools/list` fetch -- the `Callable[[], List[Dict]]` shape
    `mcp.client.ToolRegistry` expects. Same exception-group unwrap as
    `call_tool`."""
    try:
        return asyncio.run(_list_tools_async(server_url))
    except* Exception as eg:
        cause: BaseException = eg
        while isinstance(cause, BaseExceptionGroup) and len(cause.exceptions) == 1:
            cause = cause.exceptions[0]
        raise cause from None
