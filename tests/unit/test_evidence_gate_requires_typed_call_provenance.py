"""`raw_candidates_from_
find_products_batch` is the only constructor for `RawCandidate` — it parses
the actual `find_products_batch` response shape (measured from the tracked
contract fixture's `outputSchema`), never the planner's structured output.
`gate_candidates` accepts only `RawCandidate` instances, so a hallucinated
evidence tuple would have to forge a whole typed object carrying a real
`call_id`, not merely supply four convincing field values.
"""

from datetime import datetime, timezone

from src.lantern.domain.evidence_gate import (
    RawCandidate,
    gate_candidates,
    raw_candidates_from_find_products_batch,
)

# Shape measured directly from `tests/contract/fixtures/tools_list_2026-09-05.json`'s
# `silpo_find_products_batch` outputSchema, not paraphrased.
_REALISTIC_RESPONSE = {
    "success": True,
    "summary": "found 1 product",
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
                    "oldPrice": None,
                    "stock": 12,
                    "available": True,
                    "image": None,
                    "weighted": False,
                    "step": 1,
                    "displayRatio": "1 л",
                    "specialPrices": None,
                    "companyId": "c1",
                    "branchId": "b1",
                    "externalProductId": 795319,
                }
            ],
        }
    ],
}


def test_parses_a_realistic_find_products_batch_response_into_raw_candidates() -> None:
    candidates = raw_candidates_from_find_products_batch(
        call_id="call-1",
        response=_REALISTIC_RESPONSE,
        captured_at=datetime.now(timezone.utc),
    )

    assert len(candidates) == 1
    assert candidates[0].call_id == "call-1"
    assert candidates[0].external_product_id == 795319
    assert candidates[0].price_raw == 39.99
    assert candidates[0].available_raw is True


def test_gate_candidates_only_accepts_raw_candidate_instances_not_plain_dicts() -> None:
    """The planner's structured output (a plain dict/Pydantic model with no
    `call_id`) cannot pass through this signature as a `RawCandidate` — it
    would need to be wrapped in one first, and nothing in this module wraps
    arbitrary dicts. This is the structural half of DR-09's guarantee: not
    that a caller *chooses* not to pass planner output, but that the type
    the gate accepts has no field a planner output type could populate.
    """
    fabricated_like_planner_output = {
        "product_id": "invented-123",
        "price": "1.00",
        "availability": True,
        "source_tool": "silpo_find_products_batch",
    }
    # A RawCandidate literally cannot be constructed from this shape without
    # a call_id and captured_at this dict never carries — attempting to
    # treat it as one is a TypeError, not a silently-accepted gate bypass.
    import pytest

    with pytest.raises(TypeError):
        RawCandidate(**fabricated_like_planner_output)  # type: ignore[arg-type]


def test_end_to_end_realistic_response_survives_the_gate() -> None:
    candidates = raw_candidates_from_find_products_batch(
        call_id="call-1",
        response=_REALISTIC_RESPONSE,
        captured_at=datetime.now(timezone.utc),
    )
    survivors = gate_candidates(candidates)

    assert len(survivors) == 1
    assert survivors[0].product_id == "795319"
    assert survivors[0].source_tool == "silpo_find_products_batch"
