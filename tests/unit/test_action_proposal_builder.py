"""Found while wiring the graph nodes together (§4.2 steps 6-7 of the stage
spec): `gate_candidates` returns `EvidenceTuple`s (DR-10's deliberately
minimal audit record — no product name), but `ActionProposal.product_name`
needs one for the consent sentence. `build_action_proposals` re-pairs each
approved `EvidenceTuple` back to the `RawCandidate` it came from (matched
by `product_id`, via the same `resolve_product_id` the gate itself uses —
no second, divergent matching rule) to recover the name, and computes
`expected_delta = price * quantity` — arithmetic, never LLM-supplied
(DR-09).
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.domain.action_proposal_builder import build_action_proposals
from src.lantern.domain.evidence_gate import (
    RawCandidate,
    gate_candidates,
    raw_candidates_from_find_products_batch,
)

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

_RESPONSE = {
    "queries": [
        {
            "query": "milk",
            "products": [
                {
                    "name": "Молоко «Галичина» 2,5%",
                    "slug": "moloko-halychyna",
                    "price": 39.99,
                    "available": True,
                    "externalProductId": 795319,
                }
            ],
        },
        {
            "query": "bread",
            "products": [
                {
                    "name": "Хліб «Житній»",
                    "slug": "khlib-zhytniy",
                    "price": 0,  # rejected by the gate — must never reach a proposal
                    "available": True,
                    "externalProductId": 111,
                }
            ],
        },
    ]
}


def test_builds_one_proposal_per_gate_approved_candidate() -> None:
    raw = raw_candidates_from_find_products_batch(
        call_id="call-1", response=_RESPONSE, captured_at=_NOW
    )
    evidence = gate_candidates(raw)  # the zero-price bread is dropped here

    proposals = build_action_proposals(
        raw_candidates=raw, evidence=evidence, quantity=1
    )

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.product_name == "Молоко «Галичина» 2,5%"
    assert proposal.tool_name == "silpo_add_or_update_cart_products"
    assert proposal.quantity == Decimal("1")
    assert proposal.expected_delta == Decimal("39.99")
    assert proposal.canonical_args == {
        "productId": "795319",
        "quantity": 1,
        "addQuantity": False,
    }
    assert proposal.evidence == [evidence[0]]


def test_expected_delta_scales_with_quantity() -> None:
    raw = raw_candidates_from_find_products_batch(
        call_id="call-1", response=_RESPONSE, captured_at=_NOW
    )
    evidence = gate_candidates(raw)

    proposals = build_action_proposals(
        raw_candidates=raw, evidence=evidence, quantity=3
    )

    assert proposals[0].quantity == Decimal("3")
    assert proposals[0].expected_delta == Decimal("119.97")  # 39.99 * 3
    assert proposals[0].canonical_args["quantity"] == 3


def test_action_ids_are_unique_across_proposals() -> None:
    two_products_response = {
        "queries": [
            {
                "products": [
                    {
                        "name": "A",
                        "price": 10,
                        "available": True,
                        "externalProductId": 1,
                    }
                ]
            },
            {
                "products": [
                    {
                        "name": "B",
                        "price": 20,
                        "available": True,
                        "externalProductId": 2,
                    }
                ]
            },
        ]
    }
    raw = raw_candidates_from_find_products_batch(
        call_id="call-1", response=two_products_response, captured_at=_NOW
    )
    evidence = gate_candidates(raw)

    proposals = build_action_proposals(
        raw_candidates=raw, evidence=evidence, quantity=1
    )

    assert len({p.action_id for p in proposals}) == 2


def test_an_evidence_tuple_with_no_matching_raw_candidate_is_skipped() -> None:
    """Defensive case: if the evidence somehow can't be traced back to a
    raw candidate (should not happen in the real pipeline, since evidence
    is always derived from the same raw list), it is dropped, never
    fabricated with a placeholder name."""
    orphan_raw = RawCandidate(
        call_id="call-1",
        source_tool="silpo_find_products_batch",
        external_product_id=999,
        slug="",
        name="Ghost",
        price_raw=1,
        available_raw=True,
        captured_at=_NOW,
    )
    evidence = gate_candidates([orphan_raw])

    # An empty raw_candidates list means nothing can be traced back.
    proposals = build_action_proposals(raw_candidates=[], evidence=evidence, quantity=1)

    assert proposals == []
