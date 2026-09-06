"""DR-01: money is Decimal/minor units, coordinates are
float; quantity keeps fractional semantics
(`src/lantern/domain/normalizer.py`).

`cart.address` returns coordinates as
strings (`"latitude": "50.7429136"`), which `get_available_delivery_types`
then rejects with `-32602: expected number, received string`. The two
official MCP tools disagree on the type of the same field.
"""

from decimal import Decimal

from src.lantern.domain.normalizer import normalize_cart


def test_money_normalizes_to_decimal_and_coordinates_to_float():
    raw_cart = {
        "calculation": {"productsTotal": "639.65"},
        "address": {"latitude": "50.7429136", "longitude": "25.3206388"},
    }
    normalized = normalize_cart(raw_cart)

    assert isinstance(normalized.products_total, Decimal)
    assert normalized.products_total == Decimal("639.65")
    assert isinstance(normalized.latitude, float)
    assert isinstance(normalized.longitude, float)
