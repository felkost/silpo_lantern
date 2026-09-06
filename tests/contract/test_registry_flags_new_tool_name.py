"""F4 (docs/g1-g2-stage-spec.md): a new/renamed tool name in a `tools/list`
response must be flagged, not silently treated as equivalent to a known one
(D8's precedent — `silpo_create_shopping_cart` appeared unannounced). Scoped
to **tool names only** — validation-code drift (D9) is a different data path
entirely and is G3's job (F4b), not this registry's.
"""

from mcp import types as mcp_types

from src.lantern.mcp.client import ToolRegistry


def _list_tools_result(*names: str) -> mcp_types.ListToolsResult:
    return mcp_types.ListToolsResult(
        tools=[
            mcp_types.Tool(name=name, inputSchema={"type": "object"}) for name in names
        ]
    )


def test_first_fetch_establishes_the_baseline_without_flagging_anything() -> None:
    registry = ToolRegistry(
        fetch=lambda: _list_tools_result(
            "silpo_get_my_shopping_cart", "silpo_get_time_slots"
        ),
        ttl_seconds=900,
        now=lambda: 0.0,
    )
    cached = registry.get()
    assert cached.unknown_to_registry == set()


def test_a_new_tool_name_on_a_later_fetch_is_flagged() -> None:
    responses = [
        _list_tools_result("silpo_get_my_shopping_cart"),
        _list_tools_result("silpo_get_my_shopping_cart", "silpo_create_shopping_cart"),
    ]

    def fetch() -> mcp_types.ListToolsResult:
        return responses.pop(0)

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    registry.get()
    cached = registry.get(force_refresh=True)

    assert cached.unknown_to_registry == {"silpo_create_shopping_cart"}


def test_a_previously_flagged_name_is_not_flagged_again() -> None:
    responses = [
        _list_tools_result("a"),
        _list_tools_result("a", "b"),
        _list_tools_result("a", "b"),
    ]

    def fetch() -> mcp_types.ListToolsResult:
        return responses.pop(0)

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    registry.get()
    registry.get(force_refresh=True)
    cached = registry.get(force_refresh=True)

    assert cached.unknown_to_registry == set()
