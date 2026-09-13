"""T9/T11: `authorize_write`'s compensation branches
(C1-C9) -- each independently, mirroring `test_write_guard_authorization.py`'s
own one-baseline-flip-one-thing discipline. A compensation proposal must
pass every EXISTING branch too (consent binding, schema hash, budget
reserve) plus these; C6 in particular is the brief's own "no
auto-compensation when the cart was concurrently modified" at full
strength.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.lantern.domain.compensation import build_compensation_proposal
from src.lantern.domain.consent_hash import compute_args_hash, compute_state_hash
from src.lantern.domain.models import Cart, ConsentRecord, LineItem, Receipt
from src.lantern.safety.write_guard import (
    COMPENSATION_TOOL_ALLOWLIST,
    WRITE_TOOL_ALLOWLIST,
    authorize_write,
)

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
_REVIEWED_TOOL_HASH = "reviewed-hash-abc"

_WRITTEN_ARGS = {
    "shoppingCartId": "cart-1",
    "products": [{"productId": "p1"}],
}


def _after_cart() -> Cart:
    """The cart state a verified add write left behind -- p1 added, no
    other change."""
    return Cart(
        cart_id="cart-1",
        products_total=Decimal("587.61"),
        products=[
            LineItem(
                product_id="p1",
                name="Товар",
                quantity=Decimal("1"),
                price=Decimal("86.84"),
            )
        ],
    )


def _before_cart() -> Cart:
    return Cart(cart_id="cart-1", products_total=Decimal("500.77"), products=[])


def _receipt(**overrides: object) -> Receipt:
    defaults: dict = dict(
        action_id="orig-action-1",
        session_id="s1",
        owner="owner-hash-1",
        before_state=_before_cart().model_dump(mode="json"),
        after_state=_after_cart().model_dump(mode="json"),
        verified=True,
        status="receipt",
        reason="",
        blocker_cleared=False,
        created_at=_NOW,
    )
    defaults.update(overrides)
    return Receipt(**defaults)


def _compensation_proposal(receipt: Receipt, **kwargs: object):
    proposal = build_compensation_proposal(
        receipt, written_args=_WRITTEN_ARGS, action_id_factory=lambda: "comp-action-1"
    )
    assert proposal is not None
    if kwargs:
        proposal = proposal.model_copy(update=kwargs)
    return proposal


def _consent(proposal, **overrides: object) -> ConsentRecord:
    defaults: dict = dict(
        action_id=proposal.action_id,
        session_id="s1",
        owner="owner-hash-1",
        cart_id="cart-1",
        canonical_args=proposal.canonical_args,
        args_hash=compute_args_hash(proposal.canonical_args),
        state_hash=compute_state_hash(_after_cart()),
        created_at=_NOW,
        expires_at=_NOW + timedelta(minutes=5),
    )
    defaults.update(overrides)
    return ConsentRecord(**defaults)


def _authorize(receipt=None, proposal=None, consent=None, **overrides: object):
    receipt = receipt if receipt is not None else _receipt()
    proposal = proposal if proposal is not None else _compensation_proposal(receipt)
    consent = consent if consent is not None else _consent(proposal)
    defaults: dict = dict(
        proposal=proposal,
        consent=consent,
        re_read_cart=_after_cart(),
        owner="owner-hash-1",
        session_id="s1",
        consent_expired=False,
        reviewed_tool_hash=_REVIEWED_TOOL_HASH,
        live_tool_hash=_REVIEWED_TOOL_HASH,
        quarantined=frozenset(),
        budget_reserve_ok=True,
        receipt=receipt,
        written_args=_WRITTEN_ARGS,
    )
    defaults.update(overrides)
    return authorize_write(**defaults)


def test_baseline_compensation_is_authorized() -> None:
    """Proves the fixtures are internally consistent before every other
    test flips exactly one thing away from them."""
    decision = _authorize()
    assert decision.authorized is True, decision.reason


def test_remove_tool_is_on_the_compensation_allowlist_but_not_the_add_one() -> None:
    assert "silpo_remove_cart_products" in COMPENSATION_TOOL_ALLOWLIST
    assert "silpo_remove_cart_products" not in WRITE_TOOL_ALLOWLIST


def test_clear_shopping_cart_is_on_no_allowlist_for_any_kind() -> None:
    from src.lantern.safety.write_guard import _ALLOWLIST_BY_KIND

    for allowlist in _ALLOWLIST_BY_KIND.values():
        assert "silpo_clear_shopping_cart" not in allowlist


def test_unknown_kind_gets_an_empty_allowlist_not_a_default() -> None:
    receipt = _receipt()
    proposal = _compensation_proposal(receipt).model_copy(update={"kind": "wipe"})
    consent = _consent(proposal)
    decision = _authorize(receipt=receipt, proposal=proposal, consent=consent)
    assert decision.authorized is False
    assert "allowlist" in decision.reason


def test_c2_compensation_without_a_receipt_is_refused() -> None:
    proposal = _compensation_proposal(_receipt())
    consent = _consent(proposal)
    decision = authorize_write(
        proposal=proposal,
        consent=consent,
        re_read_cart=_after_cart(),
        owner="owner-hash-1",
        session_id="s1",
        consent_expired=False,
        reviewed_tool_hash=_REVIEWED_TOOL_HASH,
        live_tool_hash=_REVIEWED_TOOL_HASH,
        quarantined=frozenset(),
        budget_reserve_ok=True,
        receipt=None,
        written_args=_WRITTEN_ARGS,
    )
    assert decision.authorized is False
    assert "receipt" in decision.reason


def test_c3_compensation_of_an_unverified_write_is_refused() -> None:
    unverified_receipt = _receipt(
        status="unverified",
        verified=False,
        reason="read-back unreachable",
    )
    # Built from a compensable TEMPLATE sharing the same default
    # action_id, so C3's own `receipt_is_compensable` check is what
    # refuses this -- not `build_compensation_proposal`'s identical gate,
    # which would refuse to construct the proposal at all.
    proposal = _compensation_proposal(_receipt())
    consent = _consent(proposal)
    decision = _authorize(
        receipt=unverified_receipt, proposal=proposal, consent=consent
    )
    assert decision.authorized is False
    assert "compensable" in decision.reason


def test_c3_compensation_of_a_fully_cleared_write_is_refused() -> None:
    """Blocker cleared means plain success -- nothing to offer to undo."""
    cleared_receipt = _receipt(blocker_cleared=True)
    proposal = _compensation_proposal(_receipt())
    consent = _consent(proposal)
    decision = _authorize(receipt=cleared_receipt, proposal=proposal, consent=consent)
    assert decision.authorized is False


def test_c4_compensation_naming_a_different_receipt_is_refused() -> None:
    receipt = _receipt()
    other_receipt = _receipt(action_id="a-different-original-action")
    proposal = _compensation_proposal(other_receipt)
    consent = _consent(proposal)
    decision = _authorize(receipt=receipt, proposal=proposal, consent=consent)
    assert decision.authorized is False
    assert "receipt" in decision.reason


def test_c5_compensation_for_another_owner_is_refused() -> None:
    receipt = _receipt(owner="a-different-owner-hash")
    decision = _authorize(receipt=receipt)
    assert decision.authorized is False


def test_c5_compensation_for_another_session_is_refused() -> None:
    receipt = _receipt(session_id="a-different-session")
    decision = _authorize(receipt=receipt)
    assert decision.authorized is False


def test_c6_compensation_refused_when_the_cart_moved_since_the_write() -> None:
    """the brief: no auto-compensation when the cart was
    concurrently modified. C6 binds to the RECEIPT's own `after_state`,
    distinct from the pre-existing `consent.state_hash` check (which binds
    to consent time) -- isolated here by granting consent against the
    ALREADY-moved cart, so only C6 can catch the drift."""
    moved_cart = Cart(
        cart_id="cart-1",
        products_total=Decimal("627.60"),
        products=[
            *_after_cart().products,
            LineItem(
                product_id="p3",
                name="Щось інше додалось",
                quantity=Decimal("1"),
                price=Decimal("39.99"),
            ),
        ],
    )
    receipt = _receipt()
    proposal = _compensation_proposal(receipt)
    consent = _consent(proposal, state_hash=compute_state_hash(moved_cart))
    decision = _authorize(
        receipt=receipt, proposal=proposal, consent=consent, re_read_cart=moved_cart
    )
    assert decision.authorized is False
    assert "moved" in decision.reason


def test_c7_compensation_refused_when_args_are_not_the_exact_inverse() -> None:
    receipt = _receipt()
    proposal = _compensation_proposal(
        receipt,
        canonical_args={
            "shoppingCartId": "cart-1",
            "products": [{"productId": "a-wrong-id"}],
        },
    )
    consent = _consent(proposal)
    decision = _authorize(receipt=receipt, proposal=proposal, consent=consent)
    assert decision.authorized is False


def test_c7_tampered_expected_delta_is_refused() -> None:
    receipt = _receipt()
    proposal = _compensation_proposal(receipt, expected_delta=Decimal("-1.00"))
    consent = _consent(proposal)
    decision = _authorize(receipt=receipt, proposal=proposal, consent=consent)
    assert decision.authorized is False


def test_c8_an_ordinary_add_proposal_may_not_name_a_receipt() -> None:
    receipt = _receipt()
    add_args = {
        "shoppingCartId": "cart-1",
        "products": [
            {
                "productId": "p9",
                "companyId": "co-1",
                "branchId": "br-1",
                "quantity": 1,
                "addQuantity": False,
            }
        ],
    }
    from src.lantern.domain.models import ActionProposal, EvidenceTuple

    proposal = ActionProposal(
        action_id="a-add-1",
        tool_name="silpo_add_or_update_cart_products",
        product_name="Something",
        quantity=Decimal("1"),
        expected_delta=Decimal("10.00"),
        canonical_args=add_args,
        evidence=[
            EvidenceTuple(
                product_id="p9",
                price=Decimal("10.00"),
                availability=True,
                source_tool="silpo_find_products_batch",
                captured_at=_NOW,
            )
        ],
        kind="add",
        compensates_action_id="orig-action-1",  # not allowed for kind="add"
    )
    consent = _consent(proposal)
    decision = _authorize(receipt=receipt, proposal=proposal, consent=consent)
    assert decision.authorized is False


def test_c9_missing_company_and_branch_id_refuses_a_restore_form() -> None:
    receipt = _receipt(
        before_state=Cart(
            cart_id="cart-1",
            products_total=Decimal("199.95"),
            products=[
                LineItem(
                    product_id="p1",
                    name="Товар",
                    quantity=Decimal("5"),
                    price=Decimal("39.99"),
                )
            ],
        ).model_dump(mode="json"),
        after_state=Cart(
            cart_id="cart-1",
            products_total=Decimal("239.94"),
            products=[
                LineItem(
                    product_id="p1",
                    name="Товар",
                    quantity=Decimal("6"),
                    price=Decimal("39.99"),
                )
            ],
        ).model_dump(mode="json"),
    )
    proposal = build_compensation_proposal(receipt, written_args={})
    assert proposal is None  # cannot even be built -- no source for company/branch id


def test_fresh_consent_is_required_reusing_the_original_action_id_is_refused() -> None:
    receipt = _receipt()
    proposal = _compensation_proposal(receipt).model_copy(
        update={"action_id": receipt.action_id}
    )
    consent = _consent(proposal, action_id="a-completely-different-consent-id")
    decision = _authorize(receipt=receipt, proposal=proposal, consent=consent)
    assert decision.authorized is False
    assert "action_id" in decision.reason


def test_expired_compensation_consent_is_refused() -> None:
    decision = _authorize(consent_expired=True)
    assert decision.authorized is False
    assert "expired" in decision.reason


def test_removal_shape_rejects_more_than_one_product() -> None:
    receipt = _receipt()
    proposal = _compensation_proposal(
        receipt,
        canonical_args={
            "shoppingCartId": "cart-1",
            "products": [{"productId": "p1"}, {"productId": "p1"}],
        },
    )
    consent = _consent(proposal)
    decision = _authorize(receipt=receipt, proposal=proposal, consent=consent)
    assert decision.authorized is False


def test_removal_shape_rejects_extra_keys() -> None:
    receipt = _receipt()
    proposal = _compensation_proposal(
        receipt,
        canonical_args={
            "shoppingCartId": "cart-1",
            "products": [{"productId": "p1", "quantity": 1}],
        },
    )
    consent = _consent(proposal, args_hash=compute_args_hash(proposal.canonical_args))
    decision = _authorize(receipt=receipt, proposal=proposal, consent=consent)
    assert decision.authorized is False


def test_add_shape_check_is_unchanged() -> None:
    """T8: the renamed `_add_args_shape_errors` behaves byte-for-byte as
    the original `_canonical_args_shape_errors` did -- re-running
    `test_write_guard_authorization.py`'s own shape-check assertions
    directly against the renamed function."""
    from src.lantern.safety.write_guard import _add_args_shape_errors

    valid = {
        "shoppingCartId": "cart-1",
        "products": [
            {
                "productId": "p1",
                "companyId": "co-1",
                "branchId": "br-1",
                "quantity": 2,
                "addQuantity": False,
            }
        ],
    }
    assert _add_args_shape_errors(valid) == []
    assert _add_args_shape_errors({**valid, "extraKey": "x"}) != []
    assert _add_args_shape_errors({"shoppingCartId": "cart-1", "products": []}) != []
    assert (
        _add_args_shape_errors(
            {
                "shoppingCartId": "cart-1",
                "products": [valid["products"][0], valid["products"][0]],
            }
        )
        != []
    )
    # A remove-shaped payload (no companyId/branchId/quantity/addQuantity)
    # must still be refused by the ADD checker -- it is not a valid add.
    assert (
        _add_args_shape_errors(
            {"shoppingCartId": "cart-1", "products": [{"productId": "p1"}]}
        )
        != []
    )
