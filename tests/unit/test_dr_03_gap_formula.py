"""DR-03 (plan section 10): gap for order.cost.min = minOrderCost -
productsTotal, computed by code, never by the LLM. Declared failing per
plan section 21.3 — implemented at G3.

Evidence: `[I5]` section 9.1, confirmed on four independent live runs
(4 of 4): `minOrderCost` compares only against `productsTotal`, never
`total` or `totalAfterDiscounts` — bonuses and delivery fees must not
affect the gap. The epsilon rule below is kept deliberately even though the
anomaly that originally motivated it (a cart reading 594.72 against a 599
threshold with no blocking code) turned out to be a units-confusion bug —
the comparison was against `totalAfterDiscounts` instead of
`productsTotal` — not a real server inconsistency: it stays as cheap
defense-in-depth against exactly that class of mistake recurring.
"""

from decimal import Decimal

import pytest


@pytest.mark.xfail(strict=True, reason="Gap calculator not implemented until G3")
def test_gap_uses_products_total_not_total_after_discounts():
    from src.lantern.domain.diagnosis import compute_order_cost_min_gap  # noqa: F401

    gap = compute_order_cost_min_gap(
        min_order_cost=Decimal("599"),
        products_total=Decimal("559.73"),
    )
    assert gap == Decimal("39.27")


@pytest.mark.xfail(strict=True, reason="Gap calculator not implemented until G3")
def test_gap_epsilon_near_threshold_is_borderline_not_autofixed():
    from src.lantern.domain.diagnosis import compute_order_cost_min_gap  # noqa: F401

    # A gap smaller than the epsilon reads as "possibly borderline", never
    # an automatic pass — the plan's own DR-03 fail-closed rule (amendment
    # A2: kept deliberately even after the anomaly that motivated it turned
    # out to be a units bug, not a server inconsistency).
    gap = compute_order_cost_min_gap(
        min_order_cost=Decimal("599.00"),
        products_total=Decimal("598.99"),
    )
    assert gap.is_borderline is True
