"""T12: `finalize_write_outcome`'s mirrored identity rule
for a compensation's remove-form (`expect_absent=True`) -- exactly one
`removed` entry matching the expected product at the expected quantity,
and nothing else changed. The add path's own identity rule
(`expect_absent`'s default, `False`) stays byte-for-byte unchanged --
`test_write_guard_finalize_outcome.py` is the gate for that.
"""

from decimal import Decimal

from src.lantern.domain.models import Cart, LineItem
from src.lantern.safety.write_guard import finalize_write_outcome

_RESPONSE = {"success": True, "summary": "ok", "products": []}


def _cart(products_total: str, products: list = [], validations: list = []) -> Cart:
    return Cart(
        cart_id="cart-1",
        products_total=Decimal(products_total),
        products=products,
        validations=validations,
    )


def test_verified_removal_produces_a_receipt_with_a_negative_delta() -> None:
    before = _cart(
        "587.61",
        products=[
            LineItem(
                product_id="p1",
                name="Товар",
                quantity=Decimal("1"),
                price=Decimal("86.84"),
            )
        ],
    )
    after = _cart("500.77", products=[])

    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("-86.84"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),
        expect_absent=True,
    )
    assert outcome.status == "receipt"
    assert outcome.actual_delta == Decimal("-86.84")


def test_removal_read_back_showing_an_unrelated_add_is_unverified() -> None:
    """A concurrent, unrelated change landed alongside our removal -- the
    diff no longer isolates to exactly the consented removal."""
    before = _cart(
        "587.61",
        products=[
            LineItem(
                product_id="p1",
                name="Товар",
                quantity=Decimal("1"),
                price=Decimal("86.84"),
            )
        ],
    )
    after = _cart(
        "540.76",
        products=[
            LineItem(
                product_id="p2",
                name="Інший товар",
                quantity=Decimal("1"),
                price=Decimal("39.99"),
            )
        ],
    )
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("-86.84"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),
        expect_absent=True,
    )
    assert outcome.status == "unverified"


def test_removal_of_a_different_quantity_is_unverified() -> None:
    """The removed line's own quantity differs from what the compensation
    consented to remove -- e.g. a concurrent quantity change beat us to it."""
    before = _cart(
        "700.00",
        products=[
            LineItem(
                product_id="p1",
                name="Товар",
                quantity=Decimal("2"),
                price=Decimal("86.84"),
            )
        ],
    )
    after = _cart("526.32", products=[])

    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("-86.84"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),  # we consented to a 1-unit removal
        expect_absent=True,
    )
    assert outcome.status == "unverified"


def test_unreachable_read_back_after_a_removal_is_unverified_never_a_receipt() -> None:
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=None,
        before=_cart("587.61"),
        expected_delta=Decimal("-86.84"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),
        expect_absent=True,
    )
    assert outcome.status == "unverified"
    assert outcome.diff is None


def test_a_coincidentally_equal_negative_total_is_unverified() -> None:
    """A DIFFERENT product's removal happens to move the total by the same
    amount as the consented one -- we consented to remove p2, but p1
    (same price) was actually the one that disappeared. Must not be
    mistaken for the consented removal (mirrors the add-path
    identity rule)."""
    before = _cart(
        "173.68",
        products=[
            LineItem(
                product_id="p1",
                name="Товар",
                quantity=Decimal("1"),
                price=Decimal("86.84"),
            ),
            LineItem(
                product_id="p2",
                name="Інший товар",
                quantity=Decimal("1"),
                price=Decimal("86.84"),
            ),
        ],
    )
    after = _cart(
        "86.84",
        products=[
            LineItem(
                product_id="p2",
                name="Інший товар",
                quantity=Decimal("1"),
                price=Decimal("86.84"),
            )
        ],
    )
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("-86.84"),
        expected_product_id="p2",  # we consented to removing p2, but p1 vanished
        expected_quantity=Decimal("1"),
        expect_absent=True,
    )
    assert outcome.status == "unverified"


def test_removal_that_reprices_an_untouched_sibling_still_yields_a_receipt() -> None:
    """A multi-buy promotion re-prices a SIBLING line when the removed
    item leaves -- the sibling's quantity is unchanged, only its price
    moved. This is tolerated: the compensation succeeded, and the price
    move is a fact about the cart's own pricing, not about our removal."""
    before = _cart(
        "670.61",
        products=[
            LineItem(
                product_id="p1",
                name="Товар",
                quantity=Decimal("1"),
                price=Decimal("86.84"),
            ),
            LineItem(
                product_id="p2",
                name="Сусід",
                quantity=Decimal("2"),
                price=Decimal("291.885"),
            ),
        ],
    )
    after = _cart(
        "620.00",
        products=[
            LineItem(
                product_id="p2",
                name="Сусід",
                quantity=Decimal("2"),
                price=Decimal("310.00"),
            )
        ],
    )
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("-86.84"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),
        expect_absent=True,
    )
    assert outcome.status == "receipt"


def test_default_expect_absent_still_refuses_removed_items_on_the_add_path() -> None:
    """Non-regression: `expect_absent` defaults to `False`, so the
    ordinary add path's own protection against an unrelated removal is
    unchanged."""
    before = _cart(
        "10.00",
        products=[
            LineItem(
                product_id="p2",
                name="Інший товар",
                quantity=Decimal("1"),
                price=Decimal("10.00"),
            )
        ],
    )
    after = _cart("0.00", products=[])  # p2 vanished, nothing added
    outcome = finalize_write_outcome(
        _RESPONSE,
        read_back_result=after,
        before=before,
        expected_delta=Decimal("39.99"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),
    )
    assert outcome.status == "unverified"
    assert "removed" in outcome.reason
