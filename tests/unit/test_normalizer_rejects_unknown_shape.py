"""G3-F16: a malformed payload (missing required key, non-numeric total)
raises `CartShapeError` naming the problem, never a raw Pydantic
`ValidationError` that could carry unredacted payload content, and never a
silently-defaulted `Cart`.
"""

import pytest

from src.lantern.domain.normalizer import CartShapeError, normalize_cart


def test_missing_calculation_raises_cart_shape_error() -> None:
    with pytest.raises(CartShapeError):
        normalize_cart({"id": "cart-1"})


def test_missing_products_total_raises_cart_shape_error() -> None:
    with pytest.raises(CartShapeError):
        normalize_cart({"id": "cart-1", "calculation": {}})


def test_non_numeric_products_total_raises_cart_shape_error() -> None:
    with pytest.raises(CartShapeError):
        normalize_cart(
            {"id": "cart-1", "calculation": {"productsTotal": "not-a-number"}}
        )


def test_validation_missing_wire_message_field_raises() -> None:
    with pytest.raises(CartShapeError):
        normalize_cart(
            {
                "id": "cart-1",
                "calculation": {
                    "productsTotal": "100.00",
                    "validations": [{"level": "error", "type": "order"}],
                },
            }
        )
