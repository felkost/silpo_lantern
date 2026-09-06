"""An inferred (guessed) branch is presented at no higher
confidence than a measured one — `branch_is_inferred=True` forces
`needs_check` regardless of every other field, reproducing the current
channel's own `branch_guessed: true` flag from live evidence.
"""

from decimal import Decimal

from src.lantern.domain.disclosure import ChannelSnapshot, compare_channels


def test_inferred_branch_forces_needs_check_even_with_full_evidence() -> None:
    snapshot = ChannelSnapshot(
        delivery_type="NovaPoshta",
        branch_id="guessed-branch",
        branch_is_inferred=True,
        min_order_cost=Decimal("199"),
        delivery_cost=Decimal("129"),
        delivery_cost_map=[],
        slots_total=7,
        slots_free=2,
        item_availability=[True, True, True, True],
    )
    rows = compare_channels(Decimal("404.89"), [snapshot])

    assert rows[0].verdict == "needs_check"
    assert "branch_is_inferred" in rows[0].reason


def test_confirmed_branch_with_full_evidence_clears() -> None:
    snapshot = ChannelSnapshot(
        delivery_type="SelfPickup",
        branch_id="confirmed-branch",
        branch_is_inferred=False,
        min_order_cost=Decimal("199"),
        delivery_cost=Decimal("9"),
        delivery_cost_map=[],
        slots_total=5,
        slots_free=3,
        item_availability=[True, True, True, True],
    )
    rows = compare_channels(Decimal("404.89"), [snapshot])

    assert rows[0].verdict == "clears_now"
