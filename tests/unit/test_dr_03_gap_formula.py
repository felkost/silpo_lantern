"""DR-03: gap for order.cost.min = minOrderCost -
productsTotal, computed by code, never by the LLM
(`src/lantern/domain/diagnosis.py`).

Confirmed on four independent live runs
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

from src.lantern.domain.diagnosis import compute_order_cost_min_gap


def test_gap_uses_products_total_not_total_after_discounts():
    gap = compute_order_cost_min_gap(
        min_order_cost=Decimal("599"),
        products_total=Decimal("559.73"),
    )
    assert gap == Decimal("39.27")


def test_gap_epsilon_near_threshold_is_borderline_not_autofixed():
    # A gap smaller than the epsilon reads as "possibly borderline", never
    # an automatic pass — DR-03's fail-closed rule, kept deliberately even
    # after the anomaly that motivated it turned out to be a units bug,
    # not a server inconsistency.
    gap = compute_order_cost_min_gap(
        min_order_cost=Decimal("599.00"),
        products_total=Decimal("598.99"),
    )
    assert gap.is_borderline is True
