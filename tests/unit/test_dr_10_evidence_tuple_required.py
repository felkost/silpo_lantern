"""DR-10: the Evidence Gate's input shape makes an incomplete evidence
tuple unrepresentable — all four fields (product_id, price, availability,
source_tool, captured_at) are required, non-Optional.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.lantern.domain.models import EvidenceTuple


def test_evidence_tuple_requires_all_fields() -> None:
    now = datetime.now(timezone.utc)
    tuple_ = EvidenceTuple(
        product_id="p1",
        price="39.99",
        availability=True,
        source_tool="silpo_find_products_batch",
        captured_at=now,
    )
    assert tuple_.availability is True


def test_evidence_tuple_missing_price_raises() -> None:
    with pytest.raises(ValidationError):
        EvidenceTuple(
            product_id="p1",
            availability=True,
            source_tool="silpo_find_products_batch",
            captured_at=datetime.now(timezone.utc),
        )  # type: ignore[call-arg]
