"""T10/T11: the ordinary add path cannot reach the
compensation-only remove tool, proven over all 40 live tool names -- not
`reviewed_tools.json`'s 39 (`silpo_create_shopping_cart` stays
permanently quarantined and is deliberately the one name the reviewed
baseline omits; parametrising over the reviewed set alone would be the
one tool this sweep never tries).
"""

import json
from decimal import Decimal

import pytest

from src.lantern.config import PROJECT_ROOT
from src.lantern.domain.consent_hash import compute_args_hash, compute_state_hash
from src.lantern.domain.models import ActionProposal, Cart, ConsentRecord, EvidenceTuple
from src.lantern.safety.write_guard import (
    _ALLOWLIST_BY_KIND,
    WRITE_TOOL_ALLOWLIST,
    authorize_write,
    finalize_write_outcome,
)
from datetime import datetime, timedelta, timezone

_FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-07.json"
)
_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def _live_tool_names() -> list:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return [tool["name"] for tool in payload["payload"]["tools"]]


_LIVE_NAMES = _live_tool_names()


def test_the_fixture_carries_forty_names_not_the_reviewed_thirty_nine() -> None:
    assert len(_LIVE_NAMES) == 40


@pytest.mark.parametrize("tool_name", _LIVE_NAMES)
def test_every_live_tool_except_the_hero_write_is_refused_for_kind_add(
    tool_name: str,
) -> None:
    canonical_args = {
        "shoppingCartId": "cart-1",
        "products": [
            {
                "productId": "11111111-1111-1111-1111-111111111111",
                "companyId": "22222222-2222-2222-2222-222222222222",
                "branchId": "33333333-3333-3333-3333-333333333333",
                "quantity": 1,
                "addQuantity": False,
            }
        ],
    }
    proposal = ActionProposal(
        action_id="a1",
        tool_name=tool_name,
        product_name="X",
        quantity=Decimal("1"),
        expected_delta=Decimal("1.00"),
        canonical_args=canonical_args,
        evidence=[
            EvidenceTuple(
                product_id="11111111-1111-1111-1111-111111111111",
                price=Decimal("1.00"),
                availability=True,
                source_tool="silpo_find_products_batch",
                captured_at=_NOW,
            )
        ],
        kind="add",
    )
    cart = Cart(cart_id="cart-1", products_total=Decimal("139.99"))
    consent = ConsentRecord(
        action_id="a1",
        session_id="s1",
        owner="owner-1",
        cart_id="cart-1",
        canonical_args=canonical_args,
        args_hash=compute_args_hash(canonical_args),
        state_hash=compute_state_hash(cart),
        created_at=_NOW,
        expires_at=_NOW + timedelta(minutes=5),
    )
    decision = authorize_write(
        proposal=proposal,
        consent=consent,
        re_read_cart=cart,
        owner="owner-1",
        session_id="s1",
        consent_expired=False,
        reviewed_tool_hash="h",
        live_tool_hash="h",
        quarantined=frozenset(),
        budget_reserve_ok=True,
    )
    if tool_name == "silpo_add_or_update_cart_products":
        assert decision.authorized is True, decision.reason
    else:
        assert decision.authorized is False


def test_add_kind_allowlist_is_exactly_the_hero_write_tool_object() -> None:
    assert _ALLOWLIST_BY_KIND["add"] is WRITE_TOOL_ALLOWLIST
    assert "silpo_remove_cart_products" not in WRITE_TOOL_ALLOWLIST


def test_unknown_kind_gets_an_empty_allowlist_not_a_default() -> None:
    assert _ALLOWLIST_BY_KIND.get("some-future-kind", frozenset()) == frozenset()


def test_clear_shopping_cart_is_on_no_allowlist_for_any_kind() -> None:
    for allowlist in _ALLOWLIST_BY_KIND.values():
        assert "silpo_clear_shopping_cart" not in allowlist


def test_finalize_write_outcome_still_refuses_removed_items_at_the_default() -> None:
    """`expect_absent` defaults to `False` -- the add path's own
    protection against an unrelated concurrent removal is unchanged."""
    from src.lantern.domain.models import LineItem

    before = Cart(
        cart_id="cart-1",
        products_total=Decimal("10.00"),
        products=[
            LineItem(
                product_id="p2", name="X", quantity=Decimal("1"), price=Decimal("10.00")
            )
        ],
    )
    after = Cart(cart_id="cart-1", products_total=Decimal("0.00"), products=[])
    outcome = finalize_write_outcome(
        {"success": True, "summary": "", "products": []},
        read_back_result=after,
        before=before,
        expected_delta=Decimal("39.99"),
        expected_product_id="p1",
        expected_quantity=Decimal("1"),
    )
    assert outcome.status == "unverified"
    assert "removed" in outcome.reason
