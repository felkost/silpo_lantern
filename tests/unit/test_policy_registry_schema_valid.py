"""`registry.yaml` validates against `registry.schema.json`, and
carries exactly six confirmed codes plus two quarantined ones.
"""

from src.lantern.policies.loader import load_registry


def test_registry_loads_and_validates() -> None:
    registry = load_registry()
    assert len(registry) == 8


def test_six_confirmed_and_two_quarantined() -> None:
    registry = load_registry()
    confirmed = [
        c
        for c in [
            "order.cost.min",
            "product.offer.stock.max",
            "product.offer.not_found",
            "timeslot.not_available",
            "order.adult.is_not_confirmed",
            "order.payment_types.disabled",
        ]
        if registry.lookup(c) is not None and registry.lookup(c).status == "active"
    ]
    assert len(confirmed) == 6

    quarantined = [
        c
        for c in ["product.offer.status.not_available", "timeslot.not_found"]
        if registry.lookup(c) is not None and registry.lookup(c).status == "quarantined"
    ]
    assert len(quarantined) == 2
