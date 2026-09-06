"""D10/D-G3-05/G3-F8: a channel reads `clears_now` only when item
availability was actually checked (all True) — a row missing that check
(`item_availability=None`), or where any item is unavailable, is
`needs_check`, never presented as an actionable recommendation on price
alone. Reproduces D12's own live confirmation that a price-clearing
channel (SelfPickup, gap -205.89) had never had its items checked there.
"""

from decimal import Decimal

from src.lantern.domain.disclosure import ChannelSnapshot, compare_channels


def _snapshot(**overrides: object) -> ChannelSnapshot:
    defaults: dict[str, object] = dict(
        delivery_type="SelfPickup",
        branch_id="branch-1",
        branch_is_inferred=False,
        min_order_cost=Decimal("199"),
        delivery_cost=Decimal("9"),
        delivery_cost_map=[],
        slots_total=5,
        slots_free=3,
        item_availability=None,
    )
    defaults.update(overrides)
    return ChannelSnapshot(**defaults)  # type: ignore[arg-type]


def test_unchecked_item_availability_forces_needs_check_even_when_price_clears() -> (
    None
):
    snapshot = _snapshot(min_order_cost=Decimal("199"))
    rows = compare_channels(Decimal("404.89"), [snapshot])

    assert rows[0].verdict == "needs_check"
    assert "item_availability_not_checked" in rows[0].reason


def test_all_items_available_and_price_clears_is_clears_now() -> None:
    snapshot = _snapshot(
        min_order_cost=Decimal("199"), item_availability=[True, True, True]
    )
    rows = compare_channels(Decimal("404.89"), [snapshot])

    assert rows[0].verdict == "clears_now"
    assert rows[0].gap < 0


def test_one_item_unavailable_forces_needs_check() -> None:
    snapshot = _snapshot(
        min_order_cost=Decimal("199"), item_availability=[True, False, True]
    )
    rows = compare_channels(Decimal("404.89"), [snapshot])

    assert rows[0].verdict == "needs_check"
    assert "some_items_unavailable_on_this_channel" in rows[0].reason
