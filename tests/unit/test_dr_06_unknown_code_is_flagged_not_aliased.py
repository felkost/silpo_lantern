"""DR-06: an unregistered validation code is flagged,
never aliased to a similarly-named registered one. Two live-observed
codes with no registry match are the concrete case.
"""

from src.lantern.domain.diagnosis import diagnose
from src.lantern.domain.models import Cart, Validation
from src.lantern.policies.loader import load_registry


def _cart_with(validation: Validation) -> Cart:
    return Cart(
        cart_id="cart-1",
        products_total="500.00",
        validations=[validation],
    )


def test_d9_quarantined_code_is_not_known_and_not_aliased() -> None:
    registry = load_registry()
    v = Validation(
        level="error",
        type="order",
        code="product.offer.status.not_available",
        context={},
    )
    diagnosis = diagnose(_cart_with(v), registry)

    assert len(diagnosis.blockers) == 1
    blocker = diagnosis.blockers[0]
    assert blocker.is_known is False
    # never aliased to the similarly-named registered code
    assert blocker.validation.code != "product.offer.not_found"
    assert blocker.policy is not None
    assert blocker.policy.status == "quarantined"


def test_entirely_unknown_code_has_no_policy_at_all() -> None:
    registry = load_registry()
    v = Validation(level="error", type="order", code="totally.made.up.code", context={})
    diagnosis = diagnose(_cart_with(v), registry)

    assert diagnosis.blockers[0].is_known is False
    assert diagnosis.blockers[0].policy is None
