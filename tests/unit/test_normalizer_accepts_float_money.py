"""A5 (kickoff audit): the declared DR-01 fixture feeds money as a string,
but the live payload gives a JSON float (`productsTotal: 404.89`,
decision D12). `to_money` must accept both, always converting via
`Decimal(str(v))` so the float's literal decimal digits are kept rather
than its binary floating-point approximation.
"""

from decimal import Decimal

from src.lantern.domain.normalizer import normalize_cart, to_money


def test_to_money_accepts_a_json_float() -> None:
    assert to_money(404.89) == Decimal("404.89")


def test_to_money_accepts_a_string() -> None:
    assert to_money("404.89") == Decimal("404.89")


def test_to_money_accepts_an_int() -> None:
    assert to_money(500) == Decimal("500")


def test_normalize_cart_accepts_float_products_total() -> None:
    raw_cart = {
        "id": "cart-1",
        "calculation": {"productsTotal": 404.89},
    }
    cart = normalize_cart(raw_cart)
    assert cart.products_total == Decimal("404.89")
    assert isinstance(cart.products_total, Decimal)
