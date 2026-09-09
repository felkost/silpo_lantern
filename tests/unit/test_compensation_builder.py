"""T1 (G8 stage spec): pure derivation of a compensation write from a
`Receipt` alone (plus the original write's own `canonical_args`, for the
two fields a receipt cannot carry). No LLM anywhere on this path -- these
tests construct `Receipt`/`Cart` data directly and never touch the graph.
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.domain.compensation import (
    build_compensation_proposal,
    compensation_arg_errors,
    derive_compensation,
)
from src.lantern.domain.models import Receipt

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def _receipt(
    *,
    before_products: list,
    after_products: list,
    before_total: str,
    after_total: str,
    status: str = "receipt",
    reason: str = "",
    blocker_cleared: bool = False,
    action_id: str = "orig-action-1",
) -> Receipt:
    return Receipt(
        action_id=action_id,
        session_id="s1",
        owner="owner-hash-1",
        before_state={
            "cart_id": "cart-1",
            "products_total": before_total,
            "products": before_products,
        },
        after_state={
            "cart_id": "cart-1",
            "products_total": after_total,
            "products": after_products,
        },
        verified=status == "receipt",
        status=status,
        reason=reason,
        blocker_cleared=blocker_cleared,
        created_at=_NOW,
    )


def test_added_line_compensates_with_the_remove_tool() -> None:
    """A write that added a brand-new line has no `quantity` to restore --
    the remove tool is the only inverse."""
    receipt = _receipt(
        before_products=[],
        after_products=[
            {"product_id": "p1", "name": "Товар", "quantity": "1", "price": "86.84"}
        ],
        before_total="500.77",
        after_total="587.61",
    )
    derived = derive_compensation(receipt, written_args={})
    assert derived is not None
    assert derived.tool_name == "silpo_remove_cart_products"
    assert derived.restore_quantity is None
    assert derived.expected_delta == Decimal("-86.84")

    proposal = build_compensation_proposal(receipt, written_args={})
    assert proposal is not None
    assert proposal.kind == "compensate"
    assert proposal.compensates_action_id == "orig-action-1"
    assert proposal.canonical_args == {
        "shoppingCartId": "cart-1",
        "products": [{"productId": "p1"}],
    }
    assert proposal.expected_delta == Decimal("-86.84")
    assert compensation_arg_errors(proposal, receipt, written_args={}) == []


def test_increased_line_compensates_with_the_add_tool_at_the_original_quantity() -> (
    None
):
    receipt = _receipt(
        before_products=[
            {"product_id": "p1", "name": "Товар", "quantity": "5", "price": "39.99"}
        ],
        after_products=[
            {"product_id": "p1", "name": "Товар", "quantity": "6", "price": "39.99"}
        ],
        before_total="199.95",
        after_total="239.94",
    )
    written_args = {
        "shoppingCartId": "cart-1",
        "products": [
            {
                "productId": "p1",
                "companyId": "co-1",
                "branchId": "br-1",
                "quantity": 6,
                "addQuantity": False,
            }
        ],
    }
    derived = derive_compensation(receipt, written_args)
    assert derived is not None
    assert derived.tool_name == "silpo_add_or_update_cart_products"
    assert derived.restore_quantity == Decimal("5")
    assert derived.expected_delta == Decimal("-39.99")

    proposal = build_compensation_proposal(receipt, written_args)
    assert proposal is not None
    product = proposal.canonical_args["products"][0]
    assert product["quantity"] == 5
    assert product["addQuantity"] is False
    assert product["companyId"] == "co-1"
    assert product["branchId"] == "br-1"
    assert compensation_arg_errors(proposal, receipt, written_args) == []


def test_expected_delta_uses_the_price_the_cart_applied_not_the_catalogue_price() -> (
    None
):
    """D40/D48: the cart applies a discount the search endpoint never
    exposes. The compensation must subtract the price the CART charged
    (86.84), never the catalogue's higher figure (96.49)."""
    receipt = _receipt(
        before_products=[],
        after_products=[
            {"product_id": "p1", "name": "Товар", "quantity": "1", "price": "86.84"}
        ],
        before_total="500.77",
        after_total="587.61",
    )
    derived = derive_compensation(receipt, written_args={})
    assert derived is not None
    assert derived.expected_delta == Decimal("-86.84")
    assert derived.expected_delta != Decimal("-96.49")


def test_no_compensation_when_the_receipt_records_no_change() -> None:
    receipt = _receipt(
        before_products=[
            {"product_id": "p1", "name": "Товар", "quantity": "1", "price": "39.99"}
        ],
        after_products=[
            {"product_id": "p1", "name": "Товар", "quantity": "1", "price": "39.99"}
        ],
        before_total="139.99",
        after_total="139.99",
    )
    assert derive_compensation(receipt, written_args={}) is None
    assert build_compensation_proposal(receipt, written_args={}) is None


def test_weighted_quantity_round_trips_as_a_json_number() -> None:
    """A 0.3kg restore must emit a float, not a Decimal-as-string, so
    `args_hash` matches the wire (DR-01)."""
    receipt = _receipt(
        before_products=[
            {
                "product_id": "p1",
                "name": "Ваговий товар",
                "quantity": "0.3",
                "price": "80.00",
            }
        ],
        after_products=[
            {
                "product_id": "p1",
                "name": "Ваговий товар",
                "quantity": "0.8",
                "price": "80.00",
            }
        ],
        before_total="24.00",
        after_total="64.00",
    )
    written_args = {
        "shoppingCartId": "cart-1",
        "products": [
            {
                "productId": "p1",
                "companyId": "co-1",
                "branchId": "br-1",
                "quantity": 0.8,
                "addQuantity": False,
            }
        ],
    }
    proposal = build_compensation_proposal(receipt, written_args)
    assert proposal is not None
    quantity = proposal.canonical_args["products"][0]["quantity"]
    assert isinstance(quantity, float)
    assert quantity == 0.3


def test_no_proposal_when_company_and_branch_id_are_absent_from_both_sources() -> None:
    """A restore-form compensation needs companyId/branchId (the add tool
    requires both), and `LineItem.company_id`/`branch_id` are optional --
    `None` on the tracked replay bundle (D-G8-12). Refuses rather than
    sending a payload the server will reject."""
    receipt = _receipt(
        before_products=[
            {"product_id": "p1", "name": "Товар", "quantity": "5", "price": "39.99"}
        ],
        after_products=[
            {"product_id": "p1", "name": "Товар", "quantity": "6", "price": "39.99"}
        ],
        before_total="199.95",
        after_total="239.94",
    )
    assert derive_compensation(receipt, written_args={}) is None
    assert build_compensation_proposal(receipt, written_args={}) is None


def test_blocker_cleared_receipt_is_not_compensable() -> None:
    receipt = _receipt(
        before_products=[],
        after_products=[
            {"product_id": "p1", "name": "Товар", "quantity": "1", "price": "86.84"}
        ],
        before_total="500.77",
        after_total="587.61",
        blocker_cleared=True,
    )
    assert derive_compensation(receipt, written_args={}) is None


def test_unverified_with_an_unexplained_reason_is_not_compensable() -> None:
    receipt = _receipt(
        before_products=[],
        after_products=[],
        before_total="500.77",
        after_total="500.77",
        status="unverified",
        reason="read-back unreachable",
    )
    assert derive_compensation(receipt, written_args={}) is None
