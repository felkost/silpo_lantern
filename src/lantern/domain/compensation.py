"""Guest-facing compensation (an earlier decision, plan section 11): a controlled,
consent-bound restoration of the cart to what it held before a write this
project performed. Pure per the "domain core does no I/O" invariant --
`derive_compensation` and `build_compensation_proposal` take a `Receipt`
and the ORIGINAL write's own `canonical_args` and produce, or refuse to
produce, the inverse write. No LLM anywhere on this path: the sentence
that names an amount of money is rendered here, in code
(`CLAUDE.md` section 4).

compensation is not always the ordinary add tool run
backwards. Candidates come from `silpo_find_products_batch`, so most
writes ADD A NEW LINE rather than increase an existing one, and the add
tool's own schema (`quantity: {"type":"number","exclusiveMinimum":0}`)
cannot express "set this line to zero" -- a write that added a line has
no inverse without `silpo_remove_cart_products`. This is a dated
divergence from plan section 11.1's "hero keeps one write-tool" sentence,
recorded as amendment A9, not presented as compliance.

a receipt is compensable only when the diff it recorded is
KNOWN, never when the state is unknown. `receipt_is_compensable` mirrors
`write_guard.finalize_write_outcome`'s own branches by their exact
`reason` text -- a verified write (status="receipt") is compensable
whenever it did not clear the blocker; two specific `unverified` reasons
are compensable because `finalize_write_outcome` only reaches them AFTER
already establishing `len(matched) == 1 and not other_changes` (our
product, and nothing else, changed) -- the diff is known and unwanted,
exactly what plan section 11 names. Every other `unverified` reason means
the state is genuinely unknown, and compensating from an unknown state is
guessing, which plan section 11's own last clause forbids.
"""

import uuid
from decimal import Decimal
from typing import Any, Callable, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

from src.lantern.domain.diagnosis import canonical_diff
from src.lantern.domain.models import (
    ActionProposal,
    Cart,
    EvidenceTuple,
    Money,
    Receipt,
)

# `finalize_write_outcome` reaches these two `reason` strings only
# after its own identity check (`len(matched) == 1 and not other_changes`)
# already passed -- so a receipt carrying either one means exactly our
# product changed and nothing else did, the diff is simply not what we
# consented to. Every other `unverified` reason (read-back unreachable, a
# `canonical_diff` invariant violation, or a diff that does not isolate to
# our product) leaves the state unknown, and is deliberately NOT here.
_COMPENSABLE_UNVERIFIED_REASONS = frozenset(
    {
        "read-back quantity does not match the consented quantity",
        "read-back cart carries a new error-level validation for the "
        "written product",
    }
)


def receipt_is_compensable(receipt: Receipt) -> bool:
    """the table, as code. A verified write is compensable exactly
    when it did not clear the blocker -- clearing the blocker is a plain
    success, nothing to offer to undo."""
    if receipt.status == "receipt":
        return not receipt.blocker_cleared
    if receipt.status == "unverified":
        return receipt.reason in _COMPENSABLE_UNVERIFIED_REASONS
    return False


class CompensationWrite(BaseModel):
    """The safety-critical subset of a compensation write, derived from a
    receipt alone (plus the original write's own args, for the two fields
    a receipt cannot carry -- see `derive_compensation`). Both the builder
    and the Write Guard's own re-derivation call `derive_compensation`, so
    there is one rule, never two that could quietly diverge."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    cart_id: str
    product_id: str
    # None means the remove-form: the write added a line that did not
    # exist before, so there is no quantity to restore -- only removal.
    restore_quantity: Optional[Decimal]
    removed_quantity: Decimal
    expected_delta: Money  # always negative
    # The price the cart applied (from after_state) -- carried through so
    # `build_compensation_proposal` never has to reverse-engineer it out
    # of `expected_delta`.
    price: Money


def _to_json_number(value: Decimal) -> Any:
    """Mirrors `action_proposal_builder._to_json_number` -- duplicated
    rather than imported across a peer module's underscore-prefixed name,
    since both modules must stay independently testable and this is four
    lines. A whole quantity becomes a plain `int`; a weighted-goods
    fraction becomes a `float`, matching what `canonical_json` would
    otherwise render as a string and diverge from the wire."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _first_product(args: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    products = args.get("products")
    if not isinstance(products, list) or not products:
        return None
    product = products[0]
    return product if isinstance(product, Mapping) else None


def derive_compensation(
    receipt: Receipt, written_args: Mapping[str, Any]
) -> Optional[CompensationWrite]:
    """The independent re-derivation both the builder and the guard call.
    Returns `None` whenever the inverse cannot be safely established --
    never a best-guess value: an unrepresentable Decimal round-trip, a
    diff that does not isolate to exactly one product, or a restore-form
    missing `companyId`/`branchId` (optional on `LineItem`, `None` on the
    tracked replay bundle) all refuse rather than guess.
    """
    if not receipt_is_compensable(receipt):
        return None

    try:
        before = Cart.model_validate(receipt.before_state)
        after = Cart.model_validate(receipt.after_state)
    except ValidationError:
        return None

    try:
        diff = canonical_diff(before, after)
    except ValueError:
        return None

    # A compensable receipt's own construction already guarantees exactly
    # one product changed and nothing else did (see this module's
    # docstring) -- re-checked here anyway, since this function must never
    # trust a caller's claim about what finalize_write_outcome decided.
    if diff.removed or len(diff.added) + len(diff.changed) != 1:
        return None

    if diff.added:
        after_item = diff.added[0]
        original_quantity = Decimal("0")
    else:
        before_item, after_item = diff.changed[0]
        original_quantity = before_item.quantity

    removed_quantity = after_item.quantity
    if original_quantity == removed_quantity:
        return None

    # The price the CART applied, from after_state -- never the catalogue
    # price -- so the delta sidesteps the discount problem measured live
    # (search reported 9.34, the cart priced it 8.41) entirely:
    # the number being subtracted is the one the cart itself charged.
    expected_delta: Money = after_item.price * (original_quantity - removed_quantity)

    if original_quantity > 0:
        tool_name = "silpo_add_or_update_cart_products"
        restore_quantity: Optional[Decimal] = original_quantity
        product = _first_product(written_args)
        if (
            product is None
            or not product.get("companyId")
            or not product.get("branchId")
        ):
            return None
    else:
        tool_name = "silpo_remove_cart_products"
        restore_quantity = None

    return CompensationWrite(
        tool_name=tool_name,
        cart_id=after.cart_id,
        product_id=after_item.product_id,
        restore_quantity=restore_quantity,
        removed_quantity=removed_quantity,
        expected_delta=expected_delta,
        price=after_item.price,
    )


def _product_name(receipt: Receipt, product_id: str) -> str:
    """The read-back cart is the only source with a human-readable name --
    the receipt's own `after_state` (or, for the remove-form, `before_state`,
    since the product is gone from `after_state`)."""
    for state in (receipt.after_state, receipt.before_state):
        for line in state.get("products", []):
            if (
                line.get("productId") == product_id
                or line.get("product_id") == product_id
            ):
                name = line.get("name")
                if isinstance(name, str):
                    return name
    return product_id


def _render_guest_text_uk(product_name: str, derived: CompensationWrite) -> str:
    """Rendered in code, not by the explainer -- this sentence names an
    amount of money, and the `explain` node is not on this path at all."""
    if derived.restore_quantity is not None:
        return (
            f"Повернути «{product_name}» до попередньої кількості "
            f"({derived.restore_quantity}), очікувана зміна суми "
            f"{derived.expected_delta} грн."
        )
    return (
        f"Прибрати «{product_name}» з кошика (додано ним же раніше), "
        f"очікувана зміна суми {derived.expected_delta} грн."
    )


def build_compensation_proposal(
    receipt: Receipt,
    written_args: Mapping[str, Any],
    action_id_factory: Optional[Callable[[], str]] = None,
) -> Optional[ActionProposal]:
    """Builds the compensation `ActionProposal` from a receipt alone --
    `action_id` is a fresh uuid4 (all three write-path tables key on
    `action_id UUID`, so the compensation cannot reuse the original write's
    id), `kind="compensate"`, `compensates_action_id=receipt.action_id`.
    """
    derived = derive_compensation(receipt, written_args)
    if derived is None:
        return None

    make_action_id = action_id_factory or (lambda: str(uuid.uuid4()))
    product_name = _product_name(receipt, derived.product_id)

    if derived.restore_quantity is not None:
        original_product = _first_product(written_args) or {}
        canonical_args: dict[str, Any] = {
            "shoppingCartId": derived.cart_id,
            "products": [
                {
                    "productId": derived.product_id,
                    "companyId": original_product["companyId"],
                    "branchId": original_product["branchId"],
                    "quantity": _to_json_number(derived.restore_quantity),
                    "addQuantity": False,
                }
            ],
        }
        quantity = derived.restore_quantity - derived.removed_quantity
    else:
        canonical_args = {
            "shoppingCartId": derived.cart_id,
            "products": [{"productId": derived.product_id}],
        }
        quantity = -derived.removed_quantity

    # the compensation's evidence is the read-back call that
    # produced `after_state` -- not a catalogue lookup, since this
    # proposal is derived from a receipt, not a product search.
    evidence: List[EvidenceTuple] = [
        EvidenceTuple(
            product_id=derived.product_id,
            price=derived.price,
            availability=True,
            source_tool="silpo_get_shopping_cart_by_id",
            captured_at=receipt.created_at,
        )
    ]

    return ActionProposal(
        action_id=make_action_id(),
        tool_name=derived.tool_name,
        product_name=product_name,
        quantity=quantity,
        expected_delta=derived.expected_delta,
        canonical_args=canonical_args,
        evidence=evidence,
        guest_text_uk=_render_guest_text_uk(product_name, derived),
        kind="compensate",
        compensates_action_id=receipt.action_id,
    )


def compensation_arg_errors(
    proposal: ActionProposal, receipt: Receipt, written_args: Mapping[str, Any]
) -> List[str]:
    """The Write Guard's own independent re-derivation, compared field by
    field against `proposal` -- excluding `action_id` (a fresh uuid4 every
    time) and `guest_text_uk` (presentation only). One rule, not
    two that could drift: this calls the exact same `derive_compensation`
    the builder does.
    """
    derived = derive_compensation(receipt, written_args)
    if derived is None:
        return ["no compensable change is recorded in this receipt"]

    errors: List[str] = []
    if proposal.tool_name != derived.tool_name:
        errors.append("compensation tool does not match the recorded write's inverse")

    args = proposal.canonical_args
    if args.get("shoppingCartId") != derived.cart_id:
        errors.append("compensation cart id does not match the receipt")

    products = args.get("products")
    product = products[0] if isinstance(products, list) and products else None
    if product is None or product.get("productId") != derived.product_id:
        errors.append("compensation product id does not match the receipt")
    elif derived.restore_quantity is not None:
        if "quantity" not in product:
            errors.append("compensation restore is missing its quantity")
        elif Decimal(str(product["quantity"])) != derived.restore_quantity:
            errors.append(
                "compensation quantity does not match the recorded write's inverse"
            )
    else:
        if "quantity" in product:
            errors.append("a removal must not carry a quantity")

    if proposal.expected_delta != derived.expected_delta:
        errors.append(
            "compensation expected_delta does not match the recorded write's inverse"
        )

    return errors


__all__ = [
    "CompensationWrite",
    "receipt_is_compensable",
    "derive_compensation",
    "build_compensation_proposal",
    "compensation_arg_errors",
]
