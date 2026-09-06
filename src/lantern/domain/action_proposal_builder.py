"""`gate_candidates` returns `EvidenceTuple`s — a deliberately
minimal audit record, with no product name — but `ActionProposal.
product_name` needs a real, human-readable one for the consent sentence
("Додати товар X"). This module re-pairs each gate-approved `EvidenceTuple`
back to the `RawCandidate` it was built from, using the exact same
`resolve_product_id` the gate itself uses for matching — one id-resolution
rule, not two that could quietly diverge.
"""

import uuid
from decimal import Decimal
from typing import Callable, List, Optional, Sequence

from src.lantern.domain.evidence_gate import RawCandidate, resolve_product_id
from src.lantern.domain.models import ActionProposal, EvidenceTuple, Money


def build_action_proposals(
    raw_candidates: Sequence[RawCandidate],
    evidence: Sequence[EvidenceTuple],
    quantity: int,
    action_id_factory: Optional[Callable[[], str]] = None,
) -> List[ActionProposal]:
    """`expected_delta = price * quantity` — arithmetic performed here, in
    code, never supplied by an LLM. `action_id_factory` defaults to
    `uuid.uuid4`; injectable for deterministic tests, matching this
    project's existing pattern of injecting `now`/`fetch` elsewhere.
    """
    make_action_id = action_id_factory or (lambda: str(uuid.uuid4()))

    by_product_id = {
        product_id: raw
        for raw in raw_candidates
        if (product_id := resolve_product_id(raw)) is not None
    }

    proposals: List[ActionProposal] = []
    for tuple_ in evidence:
        raw = by_product_id.get(tuple_.product_id)
        if raw is None:
            continue
        expected_delta: Money = tuple_.price * quantity
        proposals.append(
            ActionProposal(
                action_id=make_action_id(),
                tool_name="silpo_add_or_update_cart_products",
                product_name=raw.name,
                quantity=Decimal(quantity),
                expected_delta=expected_delta,
                canonical_args={
                    "productId": tuple_.product_id,
                    "quantity": quantity,
                    "addQuantity": False,
                },
                evidence=[tuple_],
            )
        )
    return proposals
