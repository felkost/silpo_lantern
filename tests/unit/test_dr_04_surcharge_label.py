"""DR-04: surcharge = total - productsTotal, labelled
"service fee" only where a UI-confirmed one is known (self-pickup,
9 UAH); every other channel gets neutral "difference" wording.
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
    # Cross-checked against a live capture: this cart's own
    # deliveryCost is 129, matching exactly.
    amount, label = compute_surcharge(
        total=Decimal("533.89"),
        products_total=Decimal("404.89"),
        delivery_type="NovaPoshta",
    )
    assert amount == Decimal("129.00")
    assert label == "difference"
