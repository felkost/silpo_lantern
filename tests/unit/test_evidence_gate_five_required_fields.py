"""`EvidenceTuple` has FIVE
required fields, not four — an earlier count undercounted
`captured_at`. `tests/unit/test_dr_10_evidence_tuple_required.py` only
exercises `price` missing; this enumerates all five individually so a
future field addition/removal is caught no matter which one it touches.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.lantern.domain.models import EvidenceTuple

_VALID_KWARGS = {
    "product_id": "p1",
    "price": "39.99",
    "availability": True,
    "source_tool": "silpo_find_products_batch",
    "captured_at": datetime.now(timezone.utc),
}


def test_all_five_fields_together_construct_successfully() -> None:
    tuple_ = EvidenceTuple(**_VALID_KWARGS)
    assert tuple_.product_id == "p1"


@pytest.mark.parametrize(
    "missing_field",
    ["product_id", "price", "availability", "source_tool", "captured_at"],
)
def test_missing_any_single_field_raises(missing_field: str) -> None:
    kwargs = {k: v for k, v in _VALID_KWARGS.items() if k != missing_field}
    with pytest.raises(ValidationError):
        EvidenceTuple(**kwargs)  # type: ignore[arg-type]
