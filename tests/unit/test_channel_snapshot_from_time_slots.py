"""`silpo_get_time_slots` alone supplies
most of `ChannelSnapshot` — `min_order_cost`, `delivery_cost`,
`delivery_cost_map`, `slots_total`, `slots_free` — measured directly from
the tool's own `outputSchema` in the tracked contract fixture, not assumed.

Fail-safe design, extending an established pattern (a slot list
disagreeing on a value is itself `unverified`, never silently resolved by
picking one): zero slots returned means no source for `min_order_cost`
exists at all, and `ChannelSnapshot.min_order_cost` is a required
(non-Optional) field — fabricating a value here would be an invented
fact. Slots disagreeing on
`minOrderCost` get the same fail-closed treatment.
"""

from decimal import Decimal

import pytest

from src.lantern.domain.channel_snapshot_builder import (
    AmbiguousTimeSlotDataError,
    NoTimeSlotsAvailableError,
    build_channel_snapshot_from_time_slots,
    select_timeslot_for_find_products_batch,
)

_AGREEING_RESPONSE = {
    "slots": [
        {
            "start": "2026-09-08T10:00:00Z",
            "end": "2026-09-08T12:00:00Z",
            "available": True,
            "deliveryType": "SelfPickup",
            "deliveryCost": 0,
            "deliveryCostMap": [{"cost": 0, "fromOrderCost": 199}],
            "minOrderCost": 199,
        },
        {
            "start": "2026-09-08T12:00:00Z",
            "end": "2026-09-08T14:00:00Z",
            "available": False,
            "deliveryType": "SelfPickup",
            "deliveryCost": 0,
            "deliveryCostMap": [{"cost": 0, "fromOrderCost": 199}],
            "minOrderCost": 199,
        },
    ]
}


def test_builds_a_snapshot_from_agreeing_slots() -> None:
    snapshot = build_channel_snapshot_from_time_slots(
        delivery_type="SelfPickup",
        branch_id="b1",
        branch_is_inferred=False,
        time_slots_response=_AGREEING_RESPONSE,
    )
    assert snapshot.min_order_cost == Decimal("199")
    assert snapshot.delivery_cost == Decimal("0")
    assert snapshot.slots_total == 2
    assert snapshot.slots_free == 1  # only the first slot is available=True
    assert snapshot.delivery_cost_map == [
        {"cost": Decimal("0"), "fromOrderCost": Decimal("199")}
    ]


def test_zero_slots_raises_rather_than_fabricating_a_threshold() -> None:
    with pytest.raises(NoTimeSlotsAvailableError):
        build_channel_snapshot_from_time_slots(
            delivery_type="NovaPoshta",
            branch_id="b2",
            branch_is_inferred=False,
            time_slots_response={"slots": []},
        )


def test_disagreeing_min_order_cost_across_slots_raises_not_silently_picked() -> None:
    disagreeing = {
        "slots": [
            {**_AGREEING_RESPONSE["slots"][0], "minOrderCost": 199},
            {**_AGREEING_RESPONSE["slots"][1], "minOrderCost": 599},
        ]
    }
    with pytest.raises(AmbiguousTimeSlotDataError):
        build_channel_snapshot_from_time_slots(
            delivery_type="SelfPickup",
            branch_id="b1",
            branch_is_inferred=False,
            time_slots_response=disagreeing,
        )


def test_item_availability_passes_through_when_supplied() -> None:
    snapshot = build_channel_snapshot_from_time_slots(
        delivery_type="SelfPickup",
        branch_id="b1",
        branch_is_inferred=False,
        time_slots_response=_AGREEING_RESPONSE,
        item_availability=[True, False],
    )
    assert snapshot.item_availability == [True, False]


def test_item_availability_defaults_to_none_when_not_yet_checked() -> None:
    snapshot = build_channel_snapshot_from_time_slots(
        delivery_type="SelfPickup",
        branch_id="b1",
        branch_is_inferred=False,
        time_slots_response=_AGREEING_RESPONSE,
    )
    assert snapshot.item_availability is None


def test_select_timeslot_picks_the_first_available_slot() -> None:
    response = {
        "slots": [
            {"start": "A", "end": "B", "available": False},
            {
                "start": "2026-09-08T12:00:00Z",
                "end": "2026-09-08T14:00:00Z",
                "available": True,
            },
        ]
    }
    start, end = select_timeslot_for_find_products_batch(response)
    assert start == "2026-09-08T12:00:00Z"
    assert end == "2026-09-08T14:00:00Z"


def test_select_timeslot_raises_when_no_slot_is_available() -> None:
    response = {"slots": [{"start": "A", "end": "B", "available": False}]}
    with pytest.raises(NoTimeSlotsAvailableError):
        select_timeslot_for_find_products_batch(response)
