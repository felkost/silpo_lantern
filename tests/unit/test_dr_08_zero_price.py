"""DR-08 (plan section 10): a price:0 line item is not automatically "free"
or "unavailable" — check the code, stock, and context; without proof of
suitability, it is not a candidate. Declared failing per plan section
21.3 — implemented at G3.

Evidence: `[I6]` section 2 — `Sigma(price x quantity)` exactly equals
`productsTotal`; unavailable items are not excluded from the sum, they get
`price: 0`. `[I5]` section 13.1 records the author's own prior hypothesis
("unavailable items are excluded from the sum") being disproven by this
same arithmetic check on live data — the corrected rule below is the one
that survived that check.
"""

from decimal import Decimal

import pytest


@pytest.mark.xfail(
    strict=True, reason="Availability classifier not implemented until G3"
)
def test_zero_price_item_is_not_classified_as_free_or_unavailable_by_price_alone():
    from src.lantern.domain.diagnosis import classify_line_item  # noqa: F401

    classification = classify_line_item(
        price=Decimal("0"), stock=0, error_code="product.offer.stock.max"
    )
    assert classification.is_available is False
    assert classification.reason == "product.offer.stock.max"
    # price alone must never be the sole signal
    assert classification.reason != "zero_price"


@pytest.mark.xfail(strict=True, reason="Sum invariant check not implemented until G3")
def test_sum_of_line_items_equals_products_total_including_zero_priced():
    from src.lantern.domain.diagnosis import sum_line_items  # noqa: F401

    line_items = [
        {"price": Decimal("291.25"), "quantity": 1},
        {"price": Decimal("0"), "quantity": 2},  # unavailable, still summed
    ]
    assert sum_line_items(line_items) == Decimal("291.25")
