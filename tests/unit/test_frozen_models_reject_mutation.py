"""G3-F25 (round 2, W2): `mypy --strict` does not reject an assignment to a
`frozen=True` Pydantic field — it is a runtime-only guarantee. Every
domain model must actually raise on mutation, checked here rather than
trusted from the `frozen=True` config alone.
"""

import pytest
from pydantic import ValidationError

from src.lantern.domain.models import Blocker, Cart, Validation


def test_cart_rejects_mutation() -> None:
    cart = Cart(cart_id="cart-1", products_total="100.00")
    with pytest.raises(ValidationError):
        cart.cart_id = "cart-2"  # type: ignore[misc]


def test_blocker_rejects_mutation() -> None:
    blocker = Blocker(
        validation=Validation(level="error", type="order", code="x", context={}),
        policy=None,
        is_known=False,
        product_ref="unresolved",
    )
    with pytest.raises(ValidationError):
        blocker.is_known = True  # type: ignore[misc]
