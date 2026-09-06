"""`minOrderCost` sometimes arrives as a
per-slot list (`notebooks/evidence_lab.ipynb`: `sorted({s["minOrderCost"]
for s in slots})`). Measured evidence showed `[599]` only because every
slot happened to agree — nothing rules out a real cart where slots
disagree. A multi-valued list is treated as no-threshold-available, before
any cross-source comparison against the validation context happens.
"""

from decimal import Decimal

from src.lantern.domain.diagnosis import diagnose
from src.lantern.domain.models import Validation
from src.lantern.domain.normalizer import normalize_cart
from src.lantern.policies.loader import load_registry


def test_single_valued_list_is_used_directly() -> None:
    raw_cart = {
        "id": "cart-1",
        "calculation": {"productsTotal": "404.89"},
        "minOrderCost": [599],
    }
    cart = normalize_cart(raw_cart)
    assert cart.min_order_cost == Decimal("599")


def test_multivalued_list_collapses_to_no_threshold() -> None:
    raw_cart = {
        "id": "cart-1",
        "calculation": {"productsTotal": "404.89"},
        "minOrderCost": [599, 649],
    }
    cart = normalize_cart(raw_cart)
    assert cart.min_order_cost is None


def test_multivalued_list_with_no_validation_context_is_unverified_end_to_end() -> None:
    raw_cart = {
        "id": "cart-1",
        "calculation": {"productsTotal": "404.89"},
        "minOrderCost": [599, 649],
    }
    cart = normalize_cart(raw_cart).model_copy(
        update={
            "validations": [
                Validation(
                    level="error", type="order", code="order.cost.min", context={}
                )
            ]
        }
    )
    diagnosis = diagnose(cart, load_registry())
    assert diagnosis.threshold_source == "unverified"
    assert diagnosis.gap is None
