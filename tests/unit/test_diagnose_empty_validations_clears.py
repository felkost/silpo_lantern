"""A cart with zero validations (a real cart at 1561.46,
"already clears") returns a clean, empty diagnosis rather than a gap
computed against a threshold that does not apply.
"""

from src.lantern.domain.diagnosis import diagnose
from src.lantern.domain.models import Cart
from src.lantern.policies.loader import load_registry


def test_diagnose_with_no_validations_returns_empty_diagnosis() -> None:
    registry = load_registry()
    cart = Cart(cart_id="cart-1", products_total="1561.46", validations=[])

    diagnosis = diagnose(cart, registry)

    assert diagnosis.blockers == []
    assert diagnosis.disclosures == []
    assert diagnosis.gap is None
    assert diagnosis.gap_is_borderline is False
    assert diagnosis.primary_code is None
