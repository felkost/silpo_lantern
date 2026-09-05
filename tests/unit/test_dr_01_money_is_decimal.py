"""DR-01 (plan section 10): money is Decimal/minor units, coordinates are
float; quantity keeps fractional semantics. Declared failing per plan
section 21.3 — implemented at G3.

Import happens inside the test body, not at module level, so this file
collects cleanly (and reports xfail, not a collection error) while
`src/lantern/domain/normalizer.py` does not exist yet. `strict=True` means
the moment G3 adds the implementation, this test flips to XPASS, which
pytest treats as a failure — the marker cannot be silently left in place.

Evidence: `[I5]` section 10.1 — `cart.address` returns coordinates as
strings (`"latitude": "50.7429136"`), which `get_available_delivery_types`
then rejects with `-32602: expected number, received string`. The two
official MCP tools disagree on the type of the same field.
"""

from decimal import Decimal

import pytest


@pytest.mark.xfail(strict=True, reason="Normalizer not implemented until G3")
def test_money_normalizes_to_decimal_and_coordinates_to_float():
    from src.lantern.domain.normalizer import normalize_cart  # noqa: F401

    raw_cart = {
        "calculation": {"productsTotal": "639.65"},
        "address": {"latitude": "50.7429136", "longitude": "25.3206388"},
    }
    normalized = normalize_cart(raw_cart)

    assert isinstance(normalized.products_total, Decimal)
    assert normalized.products_total == Decimal("639.65")
    assert isinstance(normalized.latitude, float)
    assert isinstance(normalized.longitude, float)
