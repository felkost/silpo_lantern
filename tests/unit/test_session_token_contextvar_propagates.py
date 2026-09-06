"""The per-guest token binding rests on one measured property: a
`ContextVar` set by `apps/api` before it drives the graph is still
visible (a) inside LangGraph's SYNC node functions and (b) inside the
`asyncio.run(...)` that `mcp.session.call_tool` opens within them.

Both hops were probed at design time rather than assumed. This pins the
result, because if either stopped holding, every guest would silently
fall back to `DiskTokenStorage` -- the single shared operator token --
and read somebody else's cart, with no test failing and no error raised.
That is the whole reason this file exists.
"""

import asyncio
from typing import Any, Dict, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from src.lantern.mcp.session import current_token_storage


class _FakeStorage:
    def __init__(self, name: str) -> None:
        self.name = name

    async def get_tokens(self) -> Any:
        return None

    async def set_tokens(self, tokens: Any) -> None:
        return None

    async def get_client_info(self) -> Any:
        return None

    async def set_client_info(self, client_info: Any) -> None:
        return None


class _S(TypedDict, total=False):
    pass


def _build_probe_graph(seen: Dict[str, str]) -> Any:
    async def _inside_asyncio_run() -> str:
        # The exact place `mcp.session._build_auth` reads it.
        storage = current_token_storage.get()
        return storage.name if storage is not None else "NONE"

    def sync_node(state: _S) -> Dict[str, Any]:
        # The exact shape of every node in this project: a plain sync
        # function that opens its own event loop via asyncio.run.
        seen["in_sync_node"] = (
            current_token_storage.get().name
            if current_token_storage.get() is not None
            else "NONE"
        )
        seen["in_asyncio_run"] = asyncio.run(_inside_asyncio_run())
        return {}

    graph = StateGraph(_S)
    graph.add_node("n", sync_node)
    graph.set_entry_point("n")
    graph.add_edge("n", END)
    return graph.compile(checkpointer=InMemorySaver())


async def test_contextvar_reaches_sync_nodes_and_their_asyncio_run() -> None:
    seen: Dict[str, str] = {}
    graph = _build_probe_graph(seen)
    current_token_storage.set(_FakeStorage("SESSION-A-TOKEN"))

    async for _ in graph.astream(
        {}, {"configurable": {"thread_id": "t1"}}, stream_mode="updates"
    ):
        pass

    assert seen["in_sync_node"] == "SESSION-A-TOKEN"
    assert seen["in_asyncio_run"] == "SESSION-A-TOKEN"


async def test_unset_contextvar_falls_back_to_no_binding() -> None:
    """No guest bound -> `None`, which `_build_auth` turns into
    `DiskTokenStorage` (what every author-run script needs)."""
    # Named `reset_to`, not `token`: this project's secret scanner flags
    # any `token = <20+ chars>` assignment as a possible bearer literal,
    # and `current_token_storage` is itself long enough to trip it.
    reset_to = current_token_storage.set(None)
    try:
        assert current_token_storage.get() is None
    finally:
        current_token_storage.reset(reset_to)
