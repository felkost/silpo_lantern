"""DR-05: deliveryCost:null is "not applicable", never
coerced to zero.
"""

from src.lantern.domain.normalizer import normalize_cart


def test_null_delivery_cost_stays_none_not_zero() -> None:
    raw_cart = {
        "id": "cart-1",
        "calculation": {"productsTotal": "100.00", "delivery": {"total": None}},
    }
    cart = normalize_cart(raw_cart)
    assert cart.delivery_cost is None


def test_zero_delivery_cost_stays_zero() -> None:
    raw_cart = {
        "id": "cart-1",
        "calculation": {"productsTotal": "100.00", "delivery": {"total": 0}},
    }
    cart = normalize_cart(raw_cart)
    from decimal import Decimal

    assert cart.delivery_cost == Decimal("0")
    assert cart.delivery_cost is not None
