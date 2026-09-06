"""D-G3-13/G3-F24: `args_hash` must not change when only dict key order
changes (or CLAUDE.md's "re-read state = consent state" check would break
on a resume where the same logical args happen to serialize in a different
order), and must change when a value actually changes.
"""

from decimal import Decimal

from src.lantern.domain.consent_hash import (
    canonical_json,
    compute_args_hash,
    compute_state_hash,
)
from src.lantern.domain.models import Cart, LineItem


def test_args_hash_is_independent_of_key_order() -> None:
    a = {"productId": "abc", "quantity": 6, "addQuantity": False}
    b = {"addQuantity": False, "quantity": 6, "productId": "abc"}
    assert compute_args_hash(a) == compute_args_hash(b)


def test_args_hash_changes_when_a_value_changes() -> None:
    a = {"productId": "abc", "quantity": 6, "addQuantity": False}
    c = {"productId": "abc", "quantity": 7, "addQuantity": False}
    assert compute_args_hash(a) != compute_args_hash(c)


def test_canonical_json_serializes_decimal_via_str_not_float() -> None:
    payload = {"price": Decimal("39.99")}
    assert '"39.99"' in canonical_json(payload)


def test_state_hash_changes_when_quantity_changes() -> None:
    before = Cart(
        cart_id="cart-1",
        products_total="119.97",
        products=[LineItem(product_id="p1", name="Milk", quantity=3, price="39.99")],
    )
    after = before.model_copy(
        update={
            "products_total": Decimal("159.96"),
            "products": [
                LineItem(product_id="p1", name="Milk", quantity=4, price="39.99")
            ],
        }
    )
    assert compute_state_hash(before) != compute_state_hash(after)


def test_state_hash_is_stable_for_identical_cart() -> None:
    cart = Cart(
        cart_id="cart-1",
        products_total="119.97",
        products=[LineItem(product_id="p1", name="Milk", quantity=3, price="39.99")],
    )
    assert compute_state_hash(cart) == compute_state_hash(cart)
