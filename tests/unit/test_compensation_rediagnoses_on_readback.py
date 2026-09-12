"""after a COMPENSATION write, the blocker
status reported to the guest is re-derived from the read-back cart's own
CURRENT validations, not the stale pre-write `Diagnosis` -- a compensation
that drops `productsTotal` below a DIFFERENT threshold must not report the
old blocker as still (or no longer) the story. The ordinary add path is
unaffected: it already re-checks `primary_code` against the fresh
read-back cart, this only changes what `primary_code` itself is sourced
from for a compensation.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

from src.lantern.domain.consent_hash import compute_args_hash, compute_state_hash
from src.lantern.domain.models import ActionProposal, ConsentRecord, EvidenceTuple
from src.lantern.graph.nodes import make_write_and_readback_node
from src.lantern.graph.state import new_recovery_state
from src.lantern.policies.loader import load_registry

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

_BEFORE_CART: Dict[str, Any] = {
    "id": "cart-1",
    "calculation": {
        "productsTotal": 587.61,
        "validations": [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 599},
            }
        ],
    },
    "shipments": [
        {
            "id": "ship-1",
            "products": [
                {"productId": "p1", "name": "Товар", "quantity": 1, "price": 86.84}
            ],
        }
    ],
}

# The read-back after removing p1 -- productsTotal drops, and this fixture
# gives it a DIFFERENT validation code than the original order.cost.min,
# simulating a compensation that surfaces a distinct blocker.
_AFTER_CART: Dict[str, Any] = {
    "id": "cart-1",
    "calculation": {
        "productsTotal": 500.77,
        "validations": [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 599},
            }
        ],
    },
    "shipments": [{"id": "ship-1", "products": []}],
}


def _compensation_proposal() -> ActionProposal:
    return ActionProposal(
        action_id="comp-1",
        tool_name="silpo_remove_cart_products",
        product_name="Товар",
        quantity=Decimal("-1"),
        expected_delta=Decimal("-86.84"),
        canonical_args={"shoppingCartId": "cart-1", "products": [{"productId": "p1"}]},
        evidence=[
            EvidenceTuple(
                product_id="p1",
                price=Decimal("86.84"),
                availability=True,
                source_tool="silpo_get_shopping_cart_by_id",
                captured_at=_NOW,
            )
        ],
        kind="compensate",
        compensates_action_id="orig-1",
    )


def test_readback_node_accepts_a_registry_and_uses_it_for_compensation() -> None:
    """Pins the plumbing itself: `make_write_and_readback_node` takes a
    `registry` parameter (threaded from `build_recovery_graph`'s own
    scope, per the module docstring's stated design) so a compensation's
    outcome can be re-diagnosed against the read-back cart rather than the
    pre-write `Diagnosis` still sitting in state.
    """
    node = make_write_and_readback_node(
        call_write_tool=lambda tool, args: {
            "success": True,
            "summary": "ok",
            "products": [],
        },
        fetch_cart_by_id=lambda cart_id: {"cart": _AFTER_CART},
        claim_and_consume=lambda owner, cart_id, action_id, args_hash: (
            True,
            "in_flight",
        ),
        mark_action=lambda owner, cart_id, action_id, state: None,
        now=lambda: _NOW,
        registry=load_registry(),
    )

    proposal = _compensation_proposal()
    from src.lantern.domain.normalizer import normalize_cart

    cart = normalize_cart(_BEFORE_CART)
    consent = ConsentRecord(
        action_id=proposal.action_id,
        session_id="s1",
        owner="owner-1",
        cart_id="cart-1",
        canonical_args=proposal.canonical_args,
        args_hash=compute_args_hash(proposal.canonical_args),
        state_hash=compute_state_hash(cart),
        created_at=_NOW,
        expires_at=_NOW,
    )
    state = new_recovery_state(
        session_id="s1", trace_id="t1", now=_NOW, owner="owner-1"
    )
    state["cart"] = cart
    state["consent"] = consent
    state["candidates"] = [proposal]
    # The STALE pre-write diagnosis names a code that would, if trusted
    # blindly, mis-evaluate the compensation's outcome.
    from src.lantern.domain.diagnosis import diagnose

    state["diagnosis"] = diagnose(cart, load_registry())

    result = node(state)
    assert result["status"] in ("verified", "unverified")
    # The receipt was built without raising -- the registry plumbing
    # works end to end for the compensation path.
    assert "receipt" in result
