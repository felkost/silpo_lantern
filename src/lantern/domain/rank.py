"""Anti-goal: "Ранжувати доречні товари з мінімальною прийнятною
доплатою, не максимізувати AOV." Directly opposes
`silpo_find_products_batch`'s own tool description (measured live)
telling a model to "ALWAYS fill the cart as close to the budget limit
as possible." Deterministic, no LLM involvement — the guest's minimal
top-up, not the retailer's maximal spend.
"""

from typing import List, Optional, Sequence

from src.lantern.domain.models import ActionProposal


def rank_candidates(
    candidates: Sequence[ActionProposal], top_n: Optional[int] = None
) -> List[ActionProposal]:
    """Ascending by `expected_delta` — the cheapest acceptable top-up first.
    Stable sort: candidates with equal delta keep their relative input
    order rather than an arbitrary one. Never mutates `candidates`.
    """
    ranked = sorted(candidates, key=lambda p: p.expected_delta)
    if top_n is not None:
        return ranked[:top_n]
    return ranked
