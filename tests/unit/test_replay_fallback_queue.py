"""the tool-name-keyed fallback queue on `ReplayBundle`.

The 18 core repeats run the REAL live planner against replayed MCP
-- and `silpo_find_products_batch`'s args carry the live planner's own
search terms, which vary run to run and therefore never match
`response_key`'s exact-args hash recorded at tape time. Without a
fallback, every such call raises `ReplayMismatch` even though the tape
holds a perfectly good response for that tool. `mcp_by_tool` is consulted
only on an args-keyed miss, never instead of it -- an exact args match
always wins, since it is strictly more specific.
"""

from datetime import datetime, timezone

import pytest

from src.lantern.graph.replay import (
    BundlePlayer,
    ReplayBundle,
    ReplayMismatch,
    response_key,
)


def _bundle(mcp=None, mcp_by_tool=None) -> ReplayBundle:
    return ReplayBundle(
        fixture_id="test-fallback",
        recorded_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
        versions={},
        inputs={"session_id": "s", "trace_id": "t", "owner": "o"},
        tool_schema_hashes={},
        mcp=mcp or {},
        mcp_by_tool=mcp_by_tool or {},
        llm={"planner": [], "explainer": []},
        expected_outcome={},
    )


def test_an_args_keyed_hit_is_served_without_consulting_the_fallback() -> None:
    exact_args = {"names": ["exact query"]}
    exact_key = response_key("silpo_find_products_batch", exact_args)
    bundle = _bundle(
        mcp={exact_key: [{"products": ["exact-match"]}]},
        mcp_by_tool={"silpo_find_products_batch": [{"products": ["fallback"]}]},
    )
    player = BundlePlayer(bundle)

    result = player.call("silpo_find_products_batch", exact_args)

    assert result == {"products": ["exact-match"]}


def test_an_args_keyed_miss_on_a_different_call_still_uses_the_fallback() -> None:
    exact_args = {"names": ["exact query"]}
    exact_key = response_key("silpo_find_products_batch", exact_args)
    bundle = _bundle(
        mcp={exact_key: [{"products": ["exact-match"]}]},
        mcp_by_tool={"silpo_find_products_batch": [{"products": ["fallback"]}]},
    )
    player = BundlePlayer(bundle)

    # Different args than what's recorded under the exact key -- misses
    # the args-keyed lookup, falls through to the tool-name queue.
    result = player.call("silpo_find_products_batch", {"names": ["different query"]})

    assert result == {"products": ["fallback"]}


def test_an_args_keyed_miss_falls_back_to_the_tool_name_queue() -> None:
    bundle = _bundle(
        mcp={},
        mcp_by_tool={
            "silpo_find_products_batch": [
                {"products": ["first"]},
                {"products": ["second"]},
            ]
        },
    )
    player = BundlePlayer(bundle)

    first = player.call("silpo_find_products_batch", {"names": ["query one"]})
    second = player.call("silpo_find_products_batch", {"names": ["query two"]})

    assert first == {"products": ["first"]}
    assert second == {"products": ["second"]}


def test_the_fallback_queue_is_consumed_in_order_and_then_raises() -> None:
    bundle = _bundle(
        mcp_by_tool={"silpo_find_products_batch": [{"products": ["only"]}]}
    )
    player = BundlePlayer(bundle)

    player.call("silpo_find_products_batch", {"names": ["a"]})
    with pytest.raises(ReplayMismatch):
        player.call("silpo_find_products_batch", {"names": ["b"]})


def test_both_args_and_tool_name_miss_raises_replay_mismatch() -> None:
    bundle = _bundle(mcp={}, mcp_by_tool={})
    player = BundlePlayer(bundle)
    with pytest.raises(ReplayMismatch):
        player.call("silpo_find_products_batch", {"names": ["anything"]})


def test_a_tool_never_recorded_in_the_fallback_queue_is_unaffected() -> None:
    """A tool with no `mcp_by_tool` entry at all (e.g. `fetch_cart_by_id`,
    which is always called with args-only precision) still raises
    normally on an args-keyed miss -- the fallback is opt-in per tool,
    not a blanket catch-all."""
    bundle = _bundle(mcp={}, mcp_by_tool={"silpo_find_products_batch": [{}]})
    player = BundlePlayer(bundle)
    with pytest.raises(ReplayMismatch):
        player.call("silpo_get_shopping_cart_by_id", {"cart_id": "x"})
