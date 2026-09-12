"""a live capture whose graph DEGRADED a channel must replay
that degradation, not skip it.

`compare_channels_node` calls `fetch_time_slots` once per delivery type
the server advertises, and catches `McpAdapterError` to drop that one
channel (`nodes.py`, "degrade-not-abort"). Live, the Silpo server
advertises three types and rejects two of them (NovaPoshta and
SelfPickup resolve no real `branchId`), so ONE call per pass succeeded
and was taped -- the two failures raised and the recorder taped nothing.

Replaying that tape, the node still makes three calls per pass. The two
that failed live now find no args-keyed entry, fall through to the
tool-name queue, and eat the responses recorded for the LATER passes --
so the third pass raises `ReplayMismatch: silpo_get_time_slots fallback
queue exhausted after 3 recorded call(s)` and the bundle can never
replay its own live run.

A refused call is part of the recorded traffic. It is taped as such and
served as such.
"""

import pytest

from src.lantern.graph.replay import BundlePlayer, ReplayBundle, response_key
from src.lantern.mcp.errors import McpAdapterError
from scripts.record_replay_bundle import TAPED_ERROR_KEY, _build_draft_from_tape

# Deliberately NOT UUID-shaped: `_build_draft_from_tape` pseudonymises
# UUID-shaped argument values, so a real-looking id here would be keyed
# under its alias and every call below would MISS the args-keyed lookup
# and reach the fallback -- which is the path these tests exist to keep
# OUT of the picture. (This module's first version used a real UUID and
# passed only because the fallback cursor was itself broken.)
_BRANCH = "branch-1"


def _tape() -> dict:
    return {
        "mcp": [
            (
                "silpo_get_time_slots",
                {"branch_id": _BRANCH, "delivery_types": ["DeliveryHome"]},
                {"slots": []},
            ),
            (
                "silpo_get_time_slots",
                {"branch_id": "", "delivery_types": ["NovaPoshta"]},
                {TAPED_ERROR_KEY: "branchId must be a valid uuid"},
            ),
        ],
        "planner": [],
        "explainer": [],
    }


def _player(draft: dict) -> BundlePlayer:
    payload = draft["payload"]
    return BundlePlayer(
        ReplayBundle(
            fixture_id="t",
            recorded_at=__import__("datetime").datetime.now(),
            versions=payload["versions"],
            inputs=payload["inputs"],
            tool_schema_hashes={},
            mcp=payload["mcp"],
            llm=payload["llm"],
            expected_outcome={},
            mcp_by_tool=payload["mcp_by_tool"],
        )
    )


def test_a_refused_call_is_kept_in_the_bundle() -> None:
    draft = _build_draft_from_tape(_tape())
    key = response_key(
        "silpo_get_time_slots", {"branch_id": "", "delivery_types": ["NovaPoshta"]}
    )
    assert (
        key in draft["payload"]["mcp"]
    ), "the refused call was dropped from the bundle"
    assert TAPED_ERROR_KEY in draft["payload"]["mcp"][key][0]


def test_the_player_raises_the_recorded_refusal() -> None:
    player = _player(_build_draft_from_tape(_tape()))

    assert player.call(
        "silpo_get_time_slots",
        {"branch_id": _BRANCH, "delivery_types": ["DeliveryHome"]},
    ) == {"slots": []}

    with pytest.raises(McpAdapterError):
        player.call(
            "silpo_get_time_slots", {"branch_id": "", "delivery_types": ["NovaPoshta"]}
        )


def test_a_refusal_does_not_consume_a_successful_response() -> None:
    """The defect in one assertion: the refused channel must not eat the
    response recorded for the next pass."""
    player = _player(_build_draft_from_tape(_tape()))

    with pytest.raises(McpAdapterError):
        player.call(
            "silpo_get_time_slots", {"branch_id": "", "delivery_types": ["NovaPoshta"]}
        )

    assert player.call(
        "silpo_get_time_slots",
        {"branch_id": _BRANCH, "delivery_types": ["DeliveryHome"]},
    ) == {"slots": []}
