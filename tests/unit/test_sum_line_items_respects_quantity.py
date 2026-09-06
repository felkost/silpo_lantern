"""G3-F4b: the pre-existing DR-08 sum test's fixture uses quantities 1 and
0, so a quantity-blind implementation (summing price alone) would pass it
identically to a correct one. This test uses a quantity greater than one
on a non-zero price, where the two implementations actually diverge.
"""

from decimal import Decimal

from src.lantern.domain.diagnosis import sum_line_items


def test_sum_multiplies_price_by_quantity() -> None:
    line_items = [
        {"price": Decimal("39.99"), "quantity": 3},
        {"price": Decimal("0"), "quantity": 2},
    ]
    # A quantity-blind sum would give 39.99; the correct sum is 119.97.
    assert sum_line_items(line_items) == Decimal("119.97")
