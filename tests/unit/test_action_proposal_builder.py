"""Found while wiring the graph nodes together (§4.2 steps 6-7 of the stage
spec): `gate_candidates` returns `EvidenceTuple`s (DR-10's deliberately
minimal audit record — no product name), but `ActionProposal.product_name`
needs one for the consent sentence. `build_action_proposals` re-pairs each
approved `EvidenceTuple` back to the `RawCandidate` it came from (matched
by `product_id`, via the same `resolve_product_id` the gate itself uses —
no second, divergent matching rule) to recover the name, and computes
`expected_delta = price * quantity_increment` — arithmetic, never
LLM-supplied (DR-09).

G5+G6 (D-G5-02/D-G5-02b): rewritten in substance, not just formatting.
`canonical_args` is now the exact, complete write-tool argument object
(`shoppingCartId` + per-product `productId`/`companyId`/`branchId`), and
the write tool's own REPLACE semantics (`addQuantity: false` means "set
the quantity to this value", not "add this many") mean the wire quantity
is `existing_cart_quantity + quantity_increment`, while `expected_delta`
and `ActionProposal.quantity` stay in terms of the increment alone — what
the guest is actually being asked to consent to adding.
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.domain.action_proposal_builder import build_action_proposals
from src.lantern.domain.evidence_gate import (
    RawCandidate,
    gate_candidates,
    raw_candidates_from_find_products_batch,
)
from src.lantern.domain.models import Cart, LineItem

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

_UUID_1 = "11111111-1111-1111-1111-111111111111"
_COMPANY = "22222222-2222-2222-2222-222222222222"
_BRANCH = "33333333-3333-3333-3333-333333333333"

_RESPONSE = {
    "queries": [
        {
            "query": "milk",
            "products": [
                {
                    "id": _UUID_1,
                    "name": "Молоко «Галичина» 2,5%",
                    "slug": "moloko-halychyna",
                    "price": 39.99,
                    "stock": 600,
                    "weighted": False,
                    "step": 1,
                    "available": True,
                    "companyId": _COMPANY,
                    "branchId": _BRANCH,
                    "externalProductId": 795319,
                }
            ],
        },
        {
            "query": "bread",
            "products": [
                {
                    "id": "44444444-4444-4444-4444-444444444444",
                    "name": "Хліб «Житній»",
                    "slug": "khlib-zhytniy",
                    "price": 0,  # rejected by the gate — must never reach a proposal
                    "stock": 10,
                    "weighted": False,
                    "step": 1,
                    "available": True,
                    "companyId": _COMPANY,
                    "branchId": _BRANCH,
                    "externalProductId": 111,
                }
            ],
        },
    ]
}


def _empty_cart() -> Cart:
    return Cart(cart_id="cart-1", products_total=Decimal("0"))


def test_builds_one_proposal_per_gate_approved_candidate() -> None:
    raw = raw_candidates_from_find_products_batch(
        call_id="call-1", response=_RESPONSE, captured_at=_NOW
    )
    evidence = gate_candidates(raw)  # the zero-price bread is dropped here

    proposals = build_action_proposals(
        raw_candidates=raw, evidence=evidence, quantity_increment=1, cart=_empty_cart()
    )

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.product_name == "Молоко «Галичина» 2,5%"
    assert proposal.tool_name == "silpo_add_or_update_cart_products"
    assert proposal.quantity == Decimal("1")
    assert proposal.expected_delta == Decimal("39.99")
    assert proposal.canonical_args == {
        "shoppingCartId": "cart-1",
        "products": [
            {
                "productId": _UUID_1,
                "companyId": _COMPANY,
                "branchId": _BRANCH,
                "quantity": 1,
                "addQuantity": False,
            }
        ],
    }
    assert proposal.evidence == [evidence[0]]


def test_expected_delta_scales_with_quantity_increment() -> None:
    raw = raw_candidates_from_find_products_batch(
        call_id="call-1", response=_RESPONSE, captured_at=_NOW
    )
    evidence = gate_candidates(raw)

    proposals = build_action_proposals(
        raw_candidates=raw, evidence=evidence, quantity_increment=3, cart=_empty_cart()
    )

    assert proposals[0].quantity == Decimal("3")
    assert proposals[0].expected_delta == Decimal("119.97")  # 39.99 * 3
    assert proposals[0].canonical_args["products"][0]["quantity"] == 3


def test_replace_semantics_adds_to_the_existing_cart_quantity() -> None:
    """D-G5-02b: the wire `quantity` is REPLACE, not ADD -- a product
    already in the cart at 5 units, asked to add 1 more, must send
    `quantity: 6`, while `expected_delta` stays the price of ONE unit."""
    raw = raw_candidates_from_find_products_batch(
        call_id="call-1", response=_RESPONSE, captured_at=_NOW
    )
    evidence = gate_candidates(raw)
    cart_with_existing_item = Cart(
        cart_id="cart-1",
        products_total=Decimal("199.95"),
        products=[
            LineItem(
                product_id=_UUID_1,
                name="Молоко «Галичина» 2,5%",
                quantity=Decimal("5"),
                price=Decimal("39.99"),
            )
        ],
    )

    proposals = build_action_proposals(
        raw_candidates=raw,
        evidence=evidence,
        quantity_increment=1,
        cart=cart_with_existing_item,
    )

    assert proposals[0].quantity == Decimal("1")  # the increment, not the total
    assert proposals[0].expected_delta == Decimal("39.99")  # one unit, not six
    assert proposals[0].canonical_args["products"][0]["quantity"] == 6  # 5 + 1
    assert proposals[0].canonical_args["products"][0]["addQuantity"] is False


def test_over_stock_candidate_is_dropped() -> None:
    over_stock_response = {
        "queries": [
            {
                "products": [
                    {
                        "id": _UUID_1,
                        "name": "Milk",
                        "slug": "milk",
                        "price": 39.99,
                        "stock": 2,
                        "weighted": False,
                        "step": 1,
                        "available": True,
                        "companyId": _COMPANY,
                        "branchId": _BRANCH,
                        "externalProductId": 1,
                    }
                ]
            }
        ]
    }
    raw = raw_candidates_from_find_products_batch(
        call_id="call-1", response=over_stock_response, captured_at=_NOW
    )
    evidence = gate_candidates(raw)

    proposals = build_action_proposals(
        raw_candidates=raw, evidence=evidence, quantity_increment=3, cart=_empty_cart()
    )

    assert proposals == []


def test_weighted_goods_quantity_must_be_a_multiple_of_step() -> None:
    weighted_response = {
        "queries": [
            {
                "products": [
                    {
                        "id": _UUID_1,
                        "name": "Cheese",
                        "slug": "cheese",
                        "price": 199.0,
                        "stock": 100,
                        "weighted": True,
                        "step": 0.5,
                        "available": True,
                        "companyId": _COMPANY,
                        "branchId": _BRANCH,
                        "externalProductId": 2,
                    }
                ]
            }
        ]
    }
    raw = raw_candidates_from_find_products_batch(
        call_id="call-1", response=weighted_response, captured_at=_NOW
    )
    evidence = gate_candidates(raw)

    # 1.5 is a valid multiple of 0.5 — this one should survive.
    proposals = build_action_proposals(
        raw_candidates=raw, evidence=evidence, quantity_increment=1, cart=_empty_cart()
    )
    assert len(proposals) == 1
    assert proposals[0].canonical_args["products"][0]["quantity"] == 1


def test_action_ids_are_unique_across_proposals() -> None:
    two_products_response = {
        "queries": [
            {
                "products": [
                    {
                        "id": _UUID_1,
                        "name": "A",
                        "slug": "a",
                        "price": 10,
                        "stock": 5,
                        "weighted": False,
                        "step": 1,
                        "available": True,
                        "companyId": _COMPANY,
                        "branchId": _BRANCH,
                        "externalProductId": 1,
                    }
                ]
            },
            {
                "products": [
                    {
                        "id": "55555555-5555-5555-5555-555555555555",
                        "name": "B",
                        "slug": "b",
                        "price": 20,
                        "stock": 5,
                        "weighted": False,
                        "step": 1,
                        "available": True,
                        "companyId": _COMPANY,
                        "branchId": _BRANCH,
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
        raw_candidates=raw, evidence=evidence, quantity_increment=1, cart=_empty_cart()
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
        product_uuid="66666666-6666-6666-6666-666666666666",
        company_id=_COMPANY,
        branch_id=_BRANCH,
        stock=10,
    )
    evidence = gate_candidates([orphan_raw])

    # An empty raw_candidates list means nothing can be traced back.
    proposals = build_action_proposals(
        raw_candidates=[], evidence=evidence, quantity_increment=1, cart=_empty_cart()
    )

    assert proposals == []
