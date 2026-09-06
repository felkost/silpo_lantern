"""Found while wiring the graph nodes together: `EvidenceTuple` is
deliberately minimal (DR-10's audit record — product_id/price/availability/
source_tool/captured_at only), but `ActionProposal.product_name` needs a
real, human-readable name for the consent sentence ("Додати товар X") —
and nothing upstream ever captured one. `RawCandidate` is the right place:
it already parses the full `find_products_batch` product row, which
carries `name` directly.
"""

from datetime import datetime, timezone

from src.lantern.domain.evidence_gate import raw_candidates_from_find_products_batch

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

_RESPONSE = {
    "queries": [
        {
            "query": "milk",
            "totalFound": 1,
            "products": [
                {
                    "id": "internal-1",
                    "name": "Молоко «Галичина» 2,5%",
                    "slug": "moloko-halychyna",
                    "price": 39.99,
                    "available": True,
                    "externalProductId": 795319,
                }
            ],
        }
    ]
}


def test_raw_candidate_carries_the_product_name() -> None:
    candidates = raw_candidates_from_find_products_batch(
        call_id="call-1", response=_RESPONSE, captured_at=_NOW
    )
    assert candidates[0].name == "Молоко «Галичина» 2,5%"


def test_missing_name_field_defaults_to_empty_string_not_a_crash() -> None:
    response = {
        "queries": [
            {
                "query": "x",
                "products": [{"externalProductId": 1, "price": 1, "available": True}],
            }
        ]
    }
    candidates = raw_candidates_from_find_products_batch(
        call_id="call-1", response=response, captured_at=_NOW
    )
    assert candidates[0].name == ""
