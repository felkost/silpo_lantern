"""G3-F3: DR-06 says blockers are error-level or an allowlisted warning —
`info` never blocks, even when a registered policy entry exists for the
code (`order.payment_types.disabled` is `confirmed` in the registry but
`level: info` on every live capture so far).
"""

from src.lantern.domain.diagnosis import diagnose
from src.lantern.domain.models import Cart, Validation
from src.lantern.policies.loader import load_registry


def test_info_level_validation_lands_in_disclosures_never_blockers() -> None:
    registry = load_registry()
    cart = Cart(
        cart_id="cart-1",
        products_total="500.00",
        validations=[
            Validation(
                level="info",
                type="order",
                code="order.payment_types.disabled",
                context={},
            )
        ],
    )
    diagnosis = diagnose(cart, registry)

    assert diagnosis.blockers == []
    assert len(diagnosis.disclosures) == 1
    assert diagnosis.disclosures[0].code == "order.payment_types.disabled"
