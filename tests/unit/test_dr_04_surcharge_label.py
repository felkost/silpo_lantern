"""DR-04 (plan section 10): surcharge = total - productsTotal, labelled
"service fee" only where the plan records a UI-confirmed one (self-pickup,
9 UAH); every other channel gets neutral "difference" wording. G3-F22.
"""

from decimal import Decimal

from src.lantern.domain.diagnosis import compute_surcharge


def test_selfpickup_surcharge_is_labelled_service_fee() -> None:
    amount, label = compute_surcharge(
        total=Decimal("208"), products_total=Decimal("199"), delivery_type="SelfPickup"
    )
    assert amount == Decimal("9")
    assert label == "service_fee"


def test_other_channel_surcharge_is_labelled_difference() -> None:
    # Cross-checked against a live capture (decision D12, 2026-09-06):
    # this cart's own deliveryCost is 129, matching exactly.
    amount, label = compute_surcharge(
        total=Decimal("533.89"),
        products_total=Decimal("404.89"),
        delivery_type="NovaPoshta",
    )
    assert amount == Decimal("129.00")
    assert label == "difference"
