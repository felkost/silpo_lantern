"""A new/renamed tool name in a `tools/list` response must be flagged, not
silently treated as equivalent to a known one — `silpo_create_shopping_cart`
appeared unannounced in a live snapshot. Scoped to **tool names only** —
validation-code drift is a different data path entirely and is not this
registry's job.
"""

from typing import Any, Dict, List

from src.lantern.mcp.client import ToolRegistry


def _list_tools_raw(*names: str) -> List[Dict[str, Any]]:
    return [{"name": name, "inputSchema": {"type": "object"}} for name in names]


def test_first_fetch_establishes_the_baseline_without_flagging_anything() -> None:
    registry = ToolRegistry(
        fetch=lambda: _list_tools_raw(
            "silpo_get_my_shopping_cart", "silpo_get_time_slots"
        ),
        ttl_seconds=900,
        now=lambda: 0.0,
    )
    cached = registry.get()
    assert cached.unknown_to_registry == set()


def test_a_new_tool_name_on_a_later_fetch_is_flagged() -> None:
    responses = [
        _list_tools_raw("silpo_get_my_shopping_cart"),
        _list_tools_raw("silpo_get_my_shopping_cart", "silpo_create_shopping_cart"),
    ]

    def fetch() -> list:
        return responses.pop(0)

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    registry.get()
    cached = registry.get(force_refresh=True)

    assert cached.unknown_to_registry == {"silpo_create_shopping_cart"}


def test_a_previously_flagged_name_is_not_flagged_again() -> None:
    responses = [
        _list_tools_raw("a"),
        _list_tools_raw("a", "b"),
        _list_tools_raw("a", "b"),
    ]

    def fetch() -> list:
        return responses.pop(0)

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)
    registry.get()
    registry.get(force_refresh=True)
    cached = registry.get(force_refresh=True)

    assert cached.unknown_to_registry == set()
