"""The explicit anti-goal, directly testable: "Ранжувати
доречні товари з мінімальною прийнятною доплатою, не максимізувати AOV."
This directly opposes `silpo_find_products_batch`'s own tool description:
"ALWAYS fill the cart as close to the budget limit
as possible. Maximize the total spend." `rank_candidates` is where the
project's own stated value ("agent decides, not the raw MCP") becomes an
enforced, tested behavior rather than a pitch claim.
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.domain.models import ActionProposal, EvidenceTuple
from src.lantern.domain.rank import rank_candidates

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def _proposal(action_id: str, expected_delta: str) -> ActionProposal:
    evidence = EvidenceTuple(
        product_id=action_id,
        price=Decimal(expected_delta),
        availability=True,
        source_tool="silpo_find_products_batch",
        captured_at=_NOW,
    )
    return ActionProposal(
        action_id=action_id,
        tool_name="silpo_add_or_update_cart_products",
        product_name=f"product-{action_id}",
        quantity=Decimal("1"),
        expected_delta=Decimal(expected_delta),
        canonical_args={"productId": action_id, "quantity": 1, "addQuantity": False},
        evidence=[evidence],
    )


def test_the_cheaper_topup_ranks_first_among_equally_relevant_candidates() -> None:
    cheap = _proposal("cheap", "19.99")
    expensive = _proposal("expensive", "249.00")

    ranked = rank_candidates([expensive, cheap])

    assert [p.action_id for p in ranked] == ["cheap", "expensive"]


def test_ranking_is_stable_ascending_by_expected_delta() -> None:
    candidates = [
        _proposal("c", "50.00"),
        _proposal("a", "10.00"),
        _proposal("b", "30.00"),
    ]

    ranked = rank_candidates(candidates)

    assert [p.action_id for p in ranked] == ["a", "b", "c"]


def test_an_empty_candidate_list_ranks_to_an_empty_list() -> None:
    assert rank_candidates([]) == []


def test_ranking_never_mutates_the_input_list_order() -> None:
    candidates = [_proposal("b", "30.00"), _proposal("a", "10.00")]
    original_order = [p.action_id for p in candidates]

    rank_candidates(candidates)

    assert [p.action_id for p in candidates] == original_order


def test_top_n_truncates_to_the_requested_count_after_ranking() -> None:
    """Plan section 5.1: "2-3 доречні товари" — the graph shows a small,
    curated set, not every surviving candidate."""
    candidates = [
        _proposal("d", "40.00"),
        _proposal("a", "10.00"),
        _proposal("c", "30.00"),
        _proposal("b", "20.00"),
    ]

    ranked = rank_candidates(candidates, top_n=2)

    assert [p.action_id for p in ranked] == ["a", "b"]
