"""G3-F19: a validation's productId that matches no line item in the cart
becomes the explicit string "unresolved", never None and never a crash.
"""

from src.lantern.domain.diagnosis import diagnose
from src.lantern.domain.models import Cart, Validation
from src.lantern.policies.loader import load_registry


def test_dangling_product_id_resolves_to_unresolved() -> None:
    registry = load_registry()
    cart = Cart(
        cart_id="cart-1",
        products_total="100.00",
        products=[],  # no line items at all -> "ghost-id" cannot resolve
        validations=[
            Validation(
                level="error",
                type="product",
                code="product.offer.not_found",
                context={"productId": "ghost-id"},
            )
        ],
    )
    diagnosis = diagnose(cart, registry)

    assert diagnosis.blockers[0].product_ref == "unresolved"


def test_missing_product_id_also_resolves_to_unresolved() -> None:
    registry = load_registry()
    cart = Cart(cart_id="cart-1", products_total="100.00", products=[])
    diagnosis = diagnose(
        cart.model_copy(
            update={
                "validations": [
                    Validation(
                        level="error", type="order", code="order.cost.min", context={}
                    )
                ]
            }
        ),
        registry,
    )
    assert diagnosis.blockers[0].product_ref == "unresolved"
