"""DR-11: the canonical before/after diff. `canonical_diff` asserts its own
totals invariant internally — a diff that would silently
understate the real delta raises instead.
"""

from decimal import Decimal

import pytest

from src.lantern.domain.diagnosis import canonical_diff
from src.lantern.domain.models import Cart, LineItem


def test_diff_detects_added_and_changed_items() -> None:
    before = Cart(
        cart_id="cart-1",
        products_total="119.97",
        products=[LineItem(product_id="p1", name="Milk", quantity=3, price="39.99")],
    )
    after = Cart(
        cart_id="cart-1",
        products_total="159.96",
        products=[LineItem(product_id="p1", name="Milk", quantity=4, price="39.99")],
    )
    diff = canonical_diff(before, after)

    assert diff.added == []
    assert diff.removed == []
    assert len(diff.changed) == 1
    assert diff.total_delta == Decimal("39.99")


def test_diff_detects_removed_item() -> None:
    before = Cart(
        cart_id="cart-1",
        products_total="39.99",
        products=[LineItem(product_id="p1", name="Milk", quantity=1, price="39.99")],
    )
    after = Cart(cart_id="cart-1", products_total="0", products=[])
    diff = canonical_diff(before, after)

    assert len(diff.removed) == 1
    assert diff.total_delta == Decimal("-39.99")


def test_diff_raises_when_totals_delta_disagrees_with_line_item_delta() -> None:
    before = Cart(
        cart_id="cart-1",
        products_total="39.99",
        products=[LineItem(product_id="p1", name="Milk", quantity=1, price="39.99")],
    )
    # productsTotal claims a much larger jump than the line-item change
    # actually accounts for — a real bug this invariant must catch.
    after = Cart(
        cart_id="cart-1",
        products_total="999.99",
        products=[LineItem(product_id="p1", name="Milk", quantity=2, price="39.99")],
    )
    with pytest.raises(ValueError):
        canonical_diff(before, after)
