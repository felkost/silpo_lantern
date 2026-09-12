"""T2-T7: `authorize_write` refuses on every declared
condition, each independently, so a write can never proceed with any one
of these checks silently missing. Each test starts from a single known-
authorized baseline and flips exactly one thing, so a green suite means
every individual refusal reason is load-bearing, not merely that *some*
refusal fires somewhere.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.lantern.domain.consent_hash import compute_args_hash, compute_state_hash
from src.lantern.domain.models import ActionProposal, Cart, ConsentRecord, EvidenceTuple
from src.lantern.safety.write_guard import WRITE_TOOL_ALLOWLIST, authorize_write

_NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

_CANONICAL_ARGS = {
    "shoppingCartId": "cart-1",
    "products": [
        {
            "productId": "11111111-1111-1111-1111-111111111111",
            "companyId": "22222222-2222-2222-2222-222222222222",
            "branchId": "33333333-3333-3333-3333-333333333333",
            "quantity": 2,
            "addQuantity": False,
        }
    ],
}

_REVIEWED_TOOL_HASH = "reviewed-hash-abc"


def _cart(cart_id: str = "cart-1") -> Cart:
    return Cart(cart_id=cart_id, products_total=Decimal("139.99"))


def _proposal(
    *, tool_name: str = "silpo_add_or_update_cart_products", action_id: str = "a1"
) -> ActionProposal:
    return ActionProposal(
        action_id=action_id,
        tool_name=tool_name,
        product_name="Milk",
        quantity=Decimal("2"),
        expected_delta=Decimal("79.98"),
        canonical_args=_CANONICAL_ARGS,
        evidence=[
            EvidenceTuple(
                product_id="11111111-1111-1111-1111-111111111111",
                price=Decimal("39.99"),
                availability=True,
                source_tool="silpo_find_products_batch",
                captured_at=_NOW,
            )
        ],
    )


def _consent(**overrides: object) -> ConsentRecord:
    defaults: dict = dict(
        action_id="a1",
        session_id="s1",
        owner="owner-hash-1",
        cart_id="cart-1",
        canonical_args=_CANONICAL_ARGS,
        args_hash=compute_args_hash(_CANONICAL_ARGS),
        state_hash=compute_state_hash(_cart()),
        created_at=_NOW,
        expires_at=_NOW + timedelta(minutes=5),
    )
    defaults.update(overrides)
    return ConsentRecord(**defaults)


def _authorize(**overrides: object) -> object:
    defaults: dict = dict(
        proposal=_proposal(),
        consent=_consent(),
        re_read_cart=_cart(),
        owner="owner-hash-1",
        session_id="s1",
        consent_expired=False,
        reviewed_tool_hash=_REVIEWED_TOOL_HASH,
        live_tool_hash=_REVIEWED_TOOL_HASH,
        quarantined=frozenset(),
        budget_reserve_ok=True,
    )
    defaults.update(overrides)
    return authorize_write(**defaults)


def test_baseline_is_authorized() -> None:
    """Proves the fixtures themselves are consistent before every other
    test relies on flipping exactly one field away from them."""
    decision = _authorize()
    assert decision.authorized is True
    assert decision.reason == ""


def test_t2_tool_outside_allowlist_is_refused() -> None:
    assert "silpo_create_shopping_cart" not in WRITE_TOOL_ALLOWLIST
    decision = _authorize(proposal=_proposal(tool_name="silpo_create_shopping_cart"))
    assert decision.authorized is False
    assert "allowlist" in decision.reason


def test_t3_expired_consent_is_refused() -> None:
    decision = _authorize(consent_expired=True)
    assert decision.authorized is False
    assert "expired" in decision.reason


def test_t4_args_hash_mismatch_is_refused() -> None:
    tampered_args = {
        **_CANONICAL_ARGS,
        "products": [{**_CANONICAL_ARGS["products"][0], "quantity": 99}],
    }
    # A proposal whose canonical_args diverge from what consent was granted for.
    tampered_proposal = _proposal().model_copy(update={"canonical_args": tampered_args})
    decision = _authorize(proposal=tampered_proposal)
    assert decision.authorized is False
    assert "args_hash" in decision.reason


def test_t5_state_hash_mismatch_is_refused() -> None:
    changed_cart = Cart(cart_id="cart-1", products_total=Decimal("999.99"))
    decision = _authorize(re_read_cart=changed_cart)
    assert decision.authorized is False
    assert "state_hash" in decision.reason


def test_t6_other_owner_is_refused() -> None:
    decision = _authorize(owner="a-different-owner-hash")
    assert decision.authorized is False
    assert "owner" in decision.reason


def test_t6_other_session_is_refused() -> None:
    decision = _authorize(session_id="a-different-session")
    assert decision.authorized is False
    assert "session_id" in decision.reason


def test_t7_schema_hash_drift_is_refused() -> None:
    decision = _authorize(live_tool_hash="a-different-live-hash")
    assert decision.authorized is False
    assert "schema hash" in decision.reason


def test_t7_quarantined_tool_is_refused() -> None:
    decision = _authorize(quarantined=frozenset({"silpo_add_or_update_cart_products"}))
    assert decision.authorized is False
    assert "quarantined" in decision.reason


def test_guest_only_action_is_refused() -> None:
    decision = _authorize(proposal=_proposal(tool_name="silpo_checkout"))
    assert decision.authorized is False


def test_action_id_mismatch_is_refused() -> None:
    decision = _authorize(proposal=_proposal(action_id="a-different-action"))
    assert decision.authorized is False
    assert "action_id" in decision.reason


def test_consent_already_consumed_is_refused() -> None:
    decision = _authorize(consent=_consent(consumed_at=_NOW))
    assert decision.authorized is False
    assert "consumed" in decision.reason


def test_t19_cart_id_changed_since_consent_is_refused() -> None:
    decision = _authorize(re_read_cart=_cart(cart_id="a-different-cart"))
    assert decision.authorized is False
    assert "cart id" in decision.reason


def test_t20_insufficient_budget_reserve_is_refused() -> None:
    decision = _authorize(budget_reserve_ok=False)
    assert decision.authorized is False
    assert "budget" in decision.reason


@pytest.mark.parametrize(
    "bad_args",
    [
        {**_CANONICAL_ARGS, "extraKey": "x"},
        {"shoppingCartId": "cart-1", "products": []},
        {
            "shoppingCartId": "cart-1",
            "products": [
                {**_CANONICAL_ARGS["products"][0]},
                {**_CANONICAL_ARGS["products"][0]},
            ],
        },
    ],
)
def test_strict_shape_check_refuses_malformed_args(bad_args: dict) -> None:
    proposal = _proposal().model_copy(update={"canonical_args": bad_args})
    consent = _consent(args_hash=compute_args_hash(bad_args), canonical_args=bad_args)
    decision = _authorize(proposal=proposal, consent=consent)
    assert decision.authorized is False
