"""DR-07: not_found outranks stock.max for the same
product.

The rule is "dedupe by code + productId", but grouping
*literally* by that pair is what an earlier draft did and it made the
priority unreachable: two different codes are two different groups by
construction, so `not_found` never got the chance to outrank anything.
Grouping is therefore by `productId` alone, with the code priority applied
inside the group — see `diagnosis._dedupe_key`'s own docstring. The first
test below is what caught the wrong version (it returned 2 blockers, not 1).

Both live order-level codes carry no productId at all, so a codeless
validation is never merged with another codeless one. The
dangling-productId case has its own file,
`test_dangling_product_id_is_explicit.py`.
"""

from src.lantern.domain.diagnosis import diagnose
from src.lantern.domain.models import Cart, LineItem, Validation
from src.lantern.policies.loader import load_registry


def test_not_found_outranks_stock_max_within_same_product_group() -> None:
    registry = load_registry()
    cart = Cart(
        cart_id="cart-1",
        products_total="100.00",
        products=[LineItem(product_id="p1", name="Item", quantity=1, price="10.00")],
        validations=[
            Validation(
                level="error",
                type="product",
                code="product.offer.stock.max",
                context={"productId": "p1"},
            ),
            Validation(
                level="error",
                type="product",
                code="product.offer.not_found",
                context={"productId": "p1"},
            ),
        ],
    )
    diagnosis = diagnose(cart, registry)

    assert len(diagnosis.blockers) == 1
    assert diagnosis.blockers[0].validation.code == "product.offer.not_found"
    assert diagnosis.blockers[0].product_ref == "p1"


def test_two_codeless_order_level_validations_are_never_merged() -> None:
    registry = load_registry()
    cart = Cart(
        cart_id="cart-1",
        products_total="100.00",
        validations=[
            Validation(level="error", type="order", code="order.cost.min", context={}),
            Validation(
                level="error",
                type="order",
                code="order.adult.is_not_confirmed",
                context={},
            ),
        ],
    )
    diagnosis = diagnose(cart, registry)

    codes = {b.validation.code for b in diagnosis.blockers}
    assert codes == {"order.cost.min", "order.adult.is_not_confirmed"}
    assert len(diagnosis.blockers) == 2
