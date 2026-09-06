"""G3-F6: money arithmetic never uses `float` — `to_money` is the only
conversion path (always via `Decimal(str(v))`), and `sum_line_items`
requires its inputs to already be `Decimal`, asserting rather than
silently coercing a `float` that could reintroduce binary rounding error.
"""

import pytest

from src.lantern.domain.diagnosis import sum_line_items
from src.lantern.domain.normalizer import to_money


def test_to_money_never_produces_a_binary_rounding_artifact() -> None:
    from decimal import Decimal

    # 0.1 + 0.2 in float is 0.30000000000000004 — to_money must never
    # reproduce that class of error when given the JSON float 404.89.
    value = to_money(404.89)
    assert value == Decimal("404.89")
    assert str(value) == "404.89"


def test_sum_line_items_rejects_float_price() -> None:
    with pytest.raises(TypeError):
        sum_line_items([{"price": 39.99, "quantity": 1}])
