"""G9 (D79): the tool-name fallback queue must stay aligned with the
tape's call order, not with its own miss count.

`mcp_by_tool` is the recorded calls for one tool IN TAPE ORDER (D-G9-05).
Its cursor only advanced on a fallback hit, so a tool called through BOTH
lookups drifted: `silpo_find_products_batch` is called twice per round --
once by `compare_channels` with names taken from the cart (args match the
tape, served by the args-keyed queue) and once by `collect_and_gate` with
the planner's own search terms (args miss under a LIVE planner, served by
the fallback). The first call left the fallback cursor at 0, so the
planner's search was answered with the availability response recorded for
`compare_channels`.

Downstream that is not a crash but a wrong-product consent: the graph
proposes a product from the wrong response, writes it, and the read-back
shows something else -- so the run ends `unverified` and reads as a system
failure when the harness caused it. Six of the eighteen G9.6 repeats
failed exactly this way.

The cursor therefore advances on EVERY call to that tool, whichever
lookup served it, so position N in the fallback queue is the tape's Nth
call to that tool.
"""

import pytest

from src.lantern.graph.replay import BundlePlayer, ReplayBundle, ReplayMismatch


def _bundle(mcp, by_tool) -> ReplayBundle:
    from datetime import datetime

    return ReplayBundle(
        fixture_id="t",
        recorded_at=datetime.now(),
        versions={},
        inputs={},
        tool_schema_hashes={},
        mcp=mcp,
        llm={"planner": [], "explainer": []},
        expected_outcome={},
        mcp_by_tool=by_tool,
    )


_TOOL = "silpo_find_products_batch"


def _player() -> BundlePlayer:
    from src.lantern.graph.replay import response_key

    availability = {"products": ["availability-check"]}
    search = {"products": ["planner-search"]}
    return BundlePlayer(
        _bundle(
            # only the compare_channels call is keyed by args; the planner
            # call's args vary run to run and never match
            {response_key(_TOOL, {"names": ["from-cart"]}): [availability]},
            {_TOOL: [availability, search]},
        )
    )


def test_the_fallback_serves_the_next_call_not_the_first_one() -> None:
    player = _player()

    assert player.call(_TOOL, {"names": ["from-cart"]}) == {
        "products": ["availability-check"]
    }
    # The planner's own terms -- a miss. The tape's SECOND call to this
    # tool is the planner's search, and that is what must come back.
    assert player.call(_TOOL, {"names": ["чай", "кава"]}) == {
        "products": ["planner-search"]
    }


def test_the_queue_is_exhausted_by_calls_through_either_lookup() -> None:
    player = _player()
    player.call(_TOOL, {"names": ["from-cart"]})
    player.call(_TOOL, {"names": ["чай"]})

    with pytest.raises(ReplayMismatch, match="exhausted"):
        player.call(_TOOL, {"names": ["ще один"]})
