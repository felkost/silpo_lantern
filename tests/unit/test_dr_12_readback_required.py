"""DR-12: re-read before write, immediate read-back after
write; a write's `success` is never treated as proof of the outcome.

Implemented at `xfail(strict=True)` removed in the same commit as
`finalize_write_outcome` itself, per this project's own rule that a
strict-xfail marker left in place after the code exists turns an XPASS
into a gate failure.

The official write tool's response is
`{success, summary, products}` only: no totals, no validations, no
checkoutWebLink. The server itself cannot say whether a blocker cleared;
only a subsequent read proves it.
"""

from decimal import Decimal

from src.lantern.domain.models import Cart, LineItem
from src.lantern.safety.write_guard import finalize_write_outcome


def _cart(cart_id: str, products_total: str, products: list) -> Cart:
    return Cart(
        cart_id=cart_id, products_total=Decimal(products_total), products=products
    )


def test_write_success_without_readback_is_unverified_not_receipt() -> None:
    mcp_write_response = {
        "success": True,
        "summary": "updated",
        "products": [{"productId": "abc", "quantity": 2}],
    }
    before = _cart("cart-1", "100", [])

    outcome = finalize_write_outcome(
        mcp_write_response,
        read_back_result=None,
        before=before,
        expected_delta=Decimal("39.99"),
        expected_product_id="abc",
        expected_quantity=Decimal("2"),
    )

    assert outcome.status == "unverified"
    assert outcome.status != "receipt"


def test_write_success_with_matching_readback_is_a_receipt() -> None:
    before = _cart("cart-1", "100.00", [])
    after = _cart(
        "cart-1",
        "179.98",  # 100.00 + (39.99 * 2), a new line item (M=0)
        [
            LineItem(
                product_id="abc",
                name="Milk",
                quantity=Decimal("2"),
                price=Decimal("39.99"),
            )
        ],
    )

    outcome = finalize_write_outcome(
        {"success": True, "summary": "updated", "products": []},
        read_back_result=after,
        before=before,
        expected_delta=Decimal("79.98"),
        expected_product_id="abc",
        expected_quantity=Decimal("2"),
    )

    assert outcome.status == "receipt"
