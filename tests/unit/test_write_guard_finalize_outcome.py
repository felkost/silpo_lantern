"""T12/T13/T13b/T13c (G5+G6 stage spec): `finalize_write_outcome` verifies
identity, not merely a matching total, and turns a raising `canonical_diff`
into `unverified` rather than letting the exception escape.
"""

from decimal import Decimal

from src.lantern.domain.models import Cart, LineItem, Validation
from src.lantern.graph.nodes import _recovery_outcome
from src.lantern.safety.write_guard import finalize_write_outcome

_RESPONSE = {"success": True, "summary": "ok", "products": []}


def _cart(products_total: str, products: list = [], validations: list = []) -> Cart:
    return Cart(
        cart_id="cart-1",
        products_total=Decimal(products_total),
        products=products,
        validations=validations,
    )


def test_t12_unreachable_readback_is_unverified() -> None:
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=None,
        before=_cart("100.00"),
        expected_delta=Decimal("39.99"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),
    )
    assert outcome.status == "unverified"
    assert outcome.diff is None


def test_t13b_matching_total_but_wrong_identity_is_unverified() -> None:
    """Someone else added a DIFFERENT item of equal price -- the total
    moved by the right amount, but this was not the consented write."""
    before = _cart("100.00")
    after = _cart(
        "139.99",
        products=[
            LineItem(
                product_id="a-different-product",
                name="Not what was consented",
                quantity=Decimal("1"),
                price=Decimal("39.99"),
            )
        ],
    )
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("39.99"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),
    )
    assert outcome.status == "unverified"


def test_wrong_quantity_is_unverified() -> None:
    before = _cart("100.00")
    after = _cart(
        "139.99",
        products=[
            LineItem(
                product_id="p1",
                name="Milk",
                quantity=Decimal("1"),
                price=Decimal("39.99"),
            )
        ],
    )
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("39.99"),
        expected_product_id="p1",
        expected_quantity=Decimal("2"),  # consented quantity was 2, cart shows 1
    )
    assert outcome.status == "unverified"


def test_t13c_raising_canonical_diff_is_unverified_not_an_exception() -> None:
    """A `productsTotal` that disagrees with the line-item sum -- the
    concurrent-change case `canonical_diff` itself raises on -- must never
    escape as an exception; it is exactly the situation that must be
    reported as `unverified`."""
    before = _cart("100.00")
    after = _cart(
        "999.99",  # deliberately inconsistent with the line items below
        products=[
            LineItem(
                product_id="p1",
                name="Milk",
                quantity=Decimal("2"),
                price=Decimal("39.99"),
            )
        ],
    )
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("79.98"),
        expected_product_id="p1",
        expected_quantity=Decimal("2"),
    )
    assert outcome.status == "unverified"
    assert "invariant" in outcome.reason.lower()


def test_new_error_validation_on_written_product_is_unverified() -> None:
    """Over-stock or another blocker surfacing on the exact product just
    written -- the tool's own description says a quantity exceeding stock
    is accepted at write time and surfaces only later here."""
    before = _cart("100.00")
    after = _cart(
        "179.98",
        products=[
            LineItem(
                product_id="p1",
                name="Milk",
                quantity=Decimal("2"),
                price=Decimal("39.99"),
            )
        ],
        validations=[
            Validation(
                level="error",
                type="order",
                code="product.offer.stock.max",
                context={"productId": "p1", "stock": 1},
            )
        ],
    )
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("79.98"),
        expected_product_id="p1",
        expected_quantity=Decimal("2"),
    )
    assert outcome.status == "unverified"


def test_matching_identity_and_total_is_a_receipt() -> None:
    before = _cart("100.00")
    after = _cart(
        "179.98",
        products=[
            LineItem(
                product_id="p1",
                name="Milk",
                quantity=Decimal("2"),
                price=Decimal("39.99"),
            )
        ],
    )
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("79.98"),
        expected_product_id="p1",
        expected_quantity=Decimal("2"),
    )
    assert outcome.status == "receipt"
    assert outcome.actual_delta == Decimal("79.98")


def test_identity_matches_but_the_cart_priced_it_differently_is_a_receipt() -> None:
    """Measured on the first live write: the search endpoint reported 9.34
    for a product the cart then priced at 8.41 -- a discount it does not
    expose (`oldPrice` was null). Identity held: exactly the consented
    product, at the consented quantity, nothing else touched.

    That is a verified outcome. Gating it on the totals being equal made
    every discounted product permanently unverifiable and left
    `CostDeltaAccuracy` nothing to measure, since a mismatch could never
    reach a receipt. The difference is recorded on the receipt instead.
    """
    before = _cart("100.00")
    after = _cart(
        "108.41",
        products=[
            LineItem(
                product_id="p1",
                name="Coffee the cart discounted",
                quantity=Decimal("1"),
                price=Decimal("8.41"),
            )
        ],
    )

    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("9.34"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),
    )

    assert outcome.status == "receipt"
    assert outcome.actual_delta == Decimal("8.41")
    assert "expected 9.34" in outcome.reason
    assert "actual 8.41" in outcome.reason


def test_a_verified_write_that_leaves_the_cart_blocked_says_so() -> None:
    """The distinction a live run forced: the write landed exactly as
    consented and `status` read `receipt`, while the guest's cart was still
    blocked by 2.98 because the cart priced the product below what the
    catalogue advertised. `status` answers "did the write do what we
    agreed"; `blocker_cleared`/`remaining_gap` answer "can I check out now",
    and only the second is what the guest asked.
    """
    still_blocked = _cart(
        "596.02",
        products=[
            LineItem(
                product_id="p1",
                name="Tea",
                quantity=Decimal("1"),
                price=Decimal("86.84"),
            )
        ],
        validations=[
            Validation(
                level="error",
                type="order",
                code="order.cost.min",
                context={"orderCostMin": 599},
            )
        ],
    )

    cleared, remaining = _recovery_outcome(still_blocked, "order.cost.min")
    assert cleared is False
    assert remaining == Decimal("2.98")

    unblocked = _cart("606.21", products=still_blocked.products, validations=[])
    assert _recovery_outcome(unblocked, "order.cost.min") == (True, None)

    # An unreachable read-back proves nothing, so it never reads as cleared.
    assert _recovery_outcome(None, "order.cost.min") == (False, None)
