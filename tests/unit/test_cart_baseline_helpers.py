"""the pure halves of `scripts/g10_cart_baseline.py` -- deciding
whether the cart needs a slot and which slot to take. The live halves are
author-run and never part of the gate."""

from scripts.g10_cart_baseline import needs_new_slot, pick_slot


def test_a_cart_with_a_lapsed_slot_needs_one() -> None:
    assert needs_new_slot([{"code": "timeslot.not_found", "level": "error"}])
    assert needs_new_slot([{"code": "timeslot.not_available", "level": "error"}])
    assert not needs_new_slot([{"code": "order.cost.min", "level": "error"}])


def test_pick_the_first_available_slot_after_now() -> None:
    slots = [
        {
            "start": "2026-09-10T06:30:00+00:00",
            "end": "2026-09-10T07:30:00+00:00",
            "available": False,
        },
        {
            "start": "2026-09-11T06:30:00+00:00",
            "end": "2026-09-11T07:30:00+00:00",
            "available": True,
        },
        {
            "start": "2026-09-11T07:30:00+00:00",
            "end": "2026-09-11T09:00:00+00:00",
            "available": True,
        },
    ]
    chosen = pick_slot(slots, now_iso="2026-09-10T19:40:00+00:00")
    assert chosen == {
        "start": "2026-09-11T06:30:00+00:00",
        "end": "2026-09-11T07:30:00+00:00",
    }


def test_no_available_slot_returns_none() -> None:
    assert (
        pick_slot(
            [{"start": "x", "end": "y", "available": False}],
            now_iso="2026-09-10T00:00:00+00:00",
        )
        is None
    )
