"""D-G3-03/G3-F2: two threshold sources for order.cost.min
(`validation.context.orderCostMin` vs. `Cart.min_order_cost` from slots)
must not silently disagree. This stage's `diagnose()` prefers the
validation's own context when present, matching D-G3-03's stated priority;
the fall-back-to-slots and disagreement-is-unverified paths are exercised
via the normalizer/diagnosis boundary in
`test_multivalued_min_order_cost_is_unverified.py`.
"""

from decimal import Decimal

from src.lantern.domain.diagnosis import diagnose
from src.lantern.domain.models import Cart, Validation
from src.lantern.policies.loader import load_registry


def test_validation_context_threshold_is_preferred_over_slots() -> None:
    registry = load_registry()
    cart = Cart(
        cart_id="cart-1",
        products_total="404.89",
        min_order_cost=Decimal("649"),  # slot value disagrees with context
        validations=[
            Validation(
                level="error",
                type="order",
                code="order.cost.min",
                context={"orderCostMin": 599},
            )
        ],
    )
    diagnosis = diagnose(cart, registry)

    assert diagnosis.threshold_source == "validation_context"
    assert diagnosis.gap == Decimal("194.11")  # 599 - 404.89, not 649 - 404.89


def test_missing_context_falls_back_to_slot_threshold() -> None:
    registry = load_registry()
    cart = Cart(
        cart_id="cart-1",
        products_total="404.89",
        min_order_cost=Decimal("599"),
        validations=[
            Validation(level="error", type="order", code="order.cost.min", context={})
        ],
    )
    diagnosis = diagnose(cart, registry)

    assert diagnosis.threshold_source == "time_slots"
    assert diagnosis.gap == Decimal("194.11")


def test_no_threshold_anywhere_is_unverified() -> None:
    registry = load_registry()
    cart = Cart(
        cart_id="cart-1",
        products_total="404.89",
        min_order_cost=None,
        validations=[
            Validation(level="error", type="order", code="order.cost.min", context={})
        ],
    )
    diagnosis = diagnose(cart, registry)

    assert diagnosis.threshold_source == "unverified"
    assert diagnosis.gap is None
