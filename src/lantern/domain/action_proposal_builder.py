"""`gate_candidates` returns `EvidenceTuple`s -- a deliberately
minimal audit record, with no product name -- but `ActionProposal.
product_name` needs a real, human-readable one for the consent sentence
("Додати товар X"). This module re-pairs each gate-approved `EvidenceTuple`
back to the `RawCandidate` it was built from, using the exact same
`resolve_product_id` the gate itself uses for matching -- one id-resolution
rule, not two that could quietly diverge.

the write tool uses REPLACE semantics
(`addQuantity: false` means "set the line's quantity to this value", not
"add this many more") -- measured live: a quantity change from 5 to
6 with `addQuantity: false` produced a delta of exactly one unit price,
not six. So for a product already in the cart at quantity `M`,
`quantity_increment` (what the guest is being asked to add) yields a wire
`quantity` of `M + quantity_increment` and an `expected_delta` of
`price * quantity_increment` -- never `price * (M + quantity_increment)`,
which would silently overcharge for every unit already in the cart.
"""

import uuid
from decimal import ROUND_CEILING, Decimal
from typing import Callable, List, Optional, Sequence, Union

from src.lantern.domain.evidence_gate import RawCandidate, resolve_product_id
from src.lantern.domain.models import ActionProposal, Cart, EvidenceTuple, Money


def _to_json_number(value: Decimal) -> Union[int, float]:
    """`canonical_args` may contain only JSON-native scalars --
    measured that `canonical_json` renders a `Decimal` as a
    JSON *string*, which would make the hashed object diverge from the
    number actually sent on the wire. A whole quantity becomes a plain
    `int`; a weighted-goods fraction (e.g. `0.5`) becomes a `float`, which
    is exactly what the live `inputSchema`'s `quantity: number` expects.
    """
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _existing_quantity(cart: Cart, product_id: str) -> Decimal:
    for line_item in cart.products:
        if line_item.product_id == product_id:
            return line_item.quantity
    return Decimal(0)


def _quantity_that_closes(
    gap: Money, price: Money, existing_quantity: Decimal, unit: Decimal
) -> Decimal:
    """The smallest total line quantity whose increase over
    `existing_quantity` is worth at least `gap`, rounded up to a whole
    `unit` (1 for a countable product, the catalogue's `step` for a
    weighted one).
    """
    exact = existing_quantity + gap / price
    return (exact / unit).to_integral_value(rounding=ROUND_CEILING) * unit


def build_action_proposals(
    raw_candidates: Sequence[RawCandidate],
    evidence: Sequence[EvidenceTuple],
    gap: Money,
    cart: Cart,
    action_id_factory: Optional[Callable[[], str]] = None,
) -> List[ActionProposal]:
    """Chooses the quantity that actually closes `gap`, then computes
    `expected_delta = price * increment`. Both are arithmetic, done here in
    code -- `action_id_factory` defaults to `uuid.uuid4`, injectable for
    deterministic tests.

    The quantity used to be `SearchIntent.quantity_hint`, a field the
    PLANNER LLM fills and which defaulted to 1. Measured across four live
    runs: every proposal came back as one unit, so a 208.10 gap was
    answered with drinks worth 9-32, and the guest could consent to a
    write that provably could not unblock their cart. That also put the
    model in charge of an amount of money, which `CLAUDE.md` reserves for
    code. The hint is no longer consulted.

    A candidate is dropped (not merely reduced in quantity) when: the
    resulting total quantity would exceed the catalogue's own `stock`
    figure, or the product is weighted and that total is not a multiple
    of its `step` -- both accepted by the write tool's own schema, both
    documented by the tool itself as surfacing only later, as a cart
    validation the guest never consented to. Dropping on
    stock is what keeps the new arithmetic honest: closing a large gap
    with a cheap product needs many units, and a candidate that cannot
    supply them is not offered at all rather than offered uselessly.
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
        if raw is None or tuple_.price <= 0:
            continue

        existing_quantity = _existing_quantity(cart, tuple_.product_id)
        unit = raw.step if (raw.weighted and raw.step) else Decimal(1)
        new_total_quantity = _quantity_that_closes(
            gap, tuple_.price, existing_quantity, unit
        )
        increment = new_total_quantity - existing_quantity

        if raw.stock is not None and new_total_quantity > raw.stock:
            continue
        if raw.weighted and raw.step and new_total_quantity % raw.step != 0:
            continue

        expected_delta: Money = tuple_.price * increment
        proposals.append(
            ActionProposal(
                action_id=make_action_id(),
                tool_name="silpo_add_or_update_cart_products",
                product_name=raw.name,
                quantity=increment,
                expected_delta=expected_delta,
                canonical_args={
                    "shoppingCartId": cart.cart_id,
                    "products": [
                        {
                            "productId": tuple_.product_id,
                            "companyId": raw.company_id,
                            "branchId": raw.branch_id,
                            "quantity": _to_json_number(new_total_quantity),
                            "addQuantity": False,
                        }
                    ],
                },
                evidence=[tuple_],
            )
        )
    return proposals
