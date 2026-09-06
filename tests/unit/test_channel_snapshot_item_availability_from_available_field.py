"""A
channel's price/slot match is not itself proof the cart's own items sell
there (a "SelfPickup AVAILABLE NOW" verdict never verified the same 9
items actually sell there under NovaPoshta). `build_item_availability`
looks up each of the cart's own line-item article codes in a
`find_products_batch` response scoped to the candidate channel — missing
from the response counts as unavailable, same as an explicit
`available: False`, never silently skipped.

Reuses `raw_candidates_from_find_products_batch` (Evidence Gate,
`src/lantern/domain/evidence_gate.py`) rather than re-parsing the response
shape a second time — one parser for one wire shape.
"""

from datetime import datetime, timezone

from src.lantern.domain.channel_snapshot_builder import build_item_availability

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

_RESPONSE = {
    "queries": [
        {
            "query": "795319",
            "totalFound": 1,
            "products": [
                {
                    "id": "i1",
                    "name": "Молоко",
                    "slug": "moloko",
                    "price": 39.99,
                    "oldPrice": None,
                    "stock": 5,
                    "available": True,
                    "image": None,
                    "weighted": False,
                    "step": 1,
                    "displayRatio": None,
                    "specialPrices": None,
                    "companyId": "c1",
                    "branchId": "b1",
                    "externalProductId": 795319,
                }
            ],
        },
        {
            "query": "111222",
            "totalFound": 1,
            "products": [
                {
                    "id": "i2",
                    "name": "Хліб",
                    "slug": "khlib",
                    "price": 25.0,
                    "oldPrice": None,
                    "stock": 0,
                    "available": False,
                    "image": None,
                    "weighted": False,
                    "step": 1,
                    "displayRatio": None,
                    "specialPrices": None,
                    "companyId": "c1",
                    "branchId": "b1",
                    "externalProductId": 111222,
                }
            ],
        },
    ]
}


def test_a_product_present_and_available_is_true() -> None:
    result = build_item_availability(
        expected_external_product_ids=[795319],
        find_products_batch_response=_RESPONSE,
        call_id="call-1",
        captured_at=_NOW,
    )
    assert result == [True]


def test_a_product_present_but_marked_unavailable_is_false() -> None:
    result = build_item_availability(
        expected_external_product_ids=[111222],
        find_products_batch_response=_RESPONSE,
        call_id="call-1",
        captured_at=_NOW,
    )
    assert result == [False]


def test_a_product_absent_from_the_response_entirely_is_false_not_skipped() -> None:
    """Absence of evidence a product sells on this channel
    is never upgraded to "assumed available" — it is unavailable until
    proven otherwise, same as an explicit False."""
    result = build_item_availability(
        expected_external_product_ids=[999999],
        find_products_batch_response=_RESPONSE,
        call_id="call-1",
        captured_at=_NOW,
    )
    assert result == [False]


def test_preserves_order_and_length_matching_the_requested_ids() -> None:
    result = build_item_availability(
        expected_external_product_ids=[111222, 999999, 795319],
        find_products_batch_response=_RESPONSE,
        call_id="call-1",
        captured_at=_NOW,
    )
    assert result == [False, False, True]
