"""D-G5-25: `checkoutWebLink`'s absence is an additional signal per the
requirements checklist ("Absence of checkoutWebLink treated as an
additional signal, not a universal equivalence to blocked"), not a field
this normalizer used to silently drop.
"""

from decimal import Decimal

from src.lantern.domain.normalizer import normalize_cart


def _raw_cart(**overrides: object) -> dict:
    base = {
        "id": "cart-1",
        "calculation": {"productsTotal": 100.0},
    }
    base.update(overrides)
    return base


def test_checkout_web_link_is_parsed_when_present() -> None:
    cart = normalize_cart(_raw_cart(checkoutWebLink="https://silpo.ua/checkout/1"))
    assert cart.checkout_web_link == "https://silpo.ua/checkout/1"


def test_checkout_web_link_is_none_when_absent() -> None:
    cart = normalize_cart(_raw_cart())
    assert cart.checkout_web_link is None
    assert cart.products_total == Decimal("100.0")
