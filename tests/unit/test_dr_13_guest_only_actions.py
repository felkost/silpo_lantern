"""DR-13 (plan section 10): checkout, payment, and age confirmation stay
the guest's own actions. `GUEST_ONLY_ACTIONS` gives the rule a real
artefact a test can check against, rather than only living in a comment.
"""

from src.lantern.domain.models import GUEST_ONLY_ACTIONS, ActionProposal


def test_guest_only_actions_are_named() -> None:
    assert "silpo_checkout" in GUEST_ONLY_ACTIONS
    assert "silpo_pay_order" in GUEST_ONLY_ACTIONS
    assert "silpo_confirm_age" in GUEST_ONLY_ACTIONS


def test_hero_write_tool_is_not_guest_only() -> None:
    assert "silpo_add_or_update_cart_products" not in GUEST_ONLY_ACTIONS


def test_action_proposal_naming_a_guest_only_tool_is_detectable() -> None:
    proposal = ActionProposal(
        action_id="a1",
        tool_name="silpo_checkout",
        product_name="n/a",
        quantity="0",
        expected_delta="0",
        canonical_args={},
        evidence=[],
    )
    # The model itself doesn't forbid construction (that's a G4/G5+G6
    # authorization-time check) — but the shape makes the violation
    # detectable by a simple membership test, which is what this rule
    # actually needs downstream.
    assert proposal.tool_name in GUEST_ONLY_ACTIONS
