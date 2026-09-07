"""The Write Guard: the single point of write authorization
(`CLAUDE.md` section 4 -- "only one node may call a write tool"). Pure per
this project's "domain core does no I/O" invariant extended to safety: this
module never calls MCP, Neon, or an LLM. It decides whether a write may
happen and, separately, whether one that already happened produced a
proven outcome. The node that performs the actual call
(`graph.nodes.make_write_and_readback_node`) is a different function in a
different file -- this module authorizes, it does not write.

`WriteDecision.authorized=False` always carries a `reason`; a refusal with
no stated cause is not acceptable here, because a Write Guard that can
refuse silently is indistinguishable from one that has a bug.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final, FrozenSet, Literal, Optional

from pydantic import BaseModel, ConfigDict

from src.lantern.domain.consent_hash import compute_args_hash, compute_state_hash
from src.lantern.domain.diagnosis import canonical_diff
from src.lantern.domain.models import (
    GUEST_ONLY_ACTIONS,
    ActionProposal,
    Cart,
    CartDiff,
    ConsentRecord,
    Money,
)

# G5+G6 (D-G5-04): never derived from a live `tools/list` annotation --
# `readOnlyHint`/`destructiveHint`/`idempotentHint` are, per plan section
# 1.2, "not a guarantee of authorization." A tool earns a place here only
# by an explicit, reviewed decision, never by virtue of appearing in a
# schema fetch.
WRITE_TOOL_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {"silpo_add_or_update_cart_products"}
)


class WriteDecision(BaseModel):
    """Whether the write may proceed, and the exact argument object that
    was checked -- never a recomputed or "close enough" object, so a
    caller cannot accidentally send something the guard never actually
    validated."""

    model_config = ConfigDict(frozen=True)

    authorized: bool
    reason: str
    canonical_args: dict[str, Any]


class WriteOutcome(BaseModel):
    """The result of a completed write attempt. `status="receipt"` is
    reachable only through a verified read-back -- never through the MCP
    response's own `success` field, which the tool's own schema documents
    as proving only that the request was accepted, not that it was
    correct (plan section 11: "success from MCP is not proof of
    anything")."""

    model_config = ConfigDict(frozen=True)

    status: Literal["receipt", "unverified"]
    reason: str
    diff: Optional[CartDiff]
    actual_delta: Optional[Money]


def _canonical_args_shape_errors(canonical_args: dict[str, Any]) -> list[str]:
    """D-G5-17: the guard's own strict shape check is the authority, not
    the live `inputSchema` -- measured (M4) that schema has no
    `additionalProperties: false`, does not require `addQuantity`, and
    lets `products` carry any number of items. A payload this project
    never intended to send (extra keys, a missing `addQuantity`, more
    than one product) must be refused here even though the live schema
    alone would accept it.
    """
    errors: list[str] = []
    allowed_top = {"shoppingCartId", "products"}
    if set(canonical_args) != allowed_top:
        errors.append(f"canonical_args top-level keys must be exactly {allowed_top}")
        return errors

    products = canonical_args.get("products")
    if not isinstance(products, list) or len(products) != 1:
        errors.append("canonical_args.products must contain exactly one product")
        return errors

    product = products[0]
    allowed_product = {"productId", "companyId", "branchId", "quantity", "addQuantity"}
    if set(product) != allowed_product:
        errors.append(f"product keys must be exactly {allowed_product}")
        return errors

    if product.get("addQuantity") is not False:
        errors.append("addQuantity must be the literal False (replace semantics)")

    quantity = product.get("quantity")
    if not isinstance(quantity, (int, float)) or isinstance(quantity, bool):
        errors.append("quantity must be a JSON number")
    elif quantity <= 0:
        errors.append("quantity must be positive")

    return errors


def authorize_write(
    proposal: ActionProposal,
    consent: ConsentRecord,
    re_read_cart: Cart,
    owner: str,
    session_id: str,
    consent_expired: bool,
    reviewed_tool_hash: str,
    live_tool_hash: str,
    quarantined: FrozenSet[str],
    budget_reserve_ok: bool,
) -> WriteDecision:
    """`owner`/`session_id`/`consent_expired`/`budget_reserve_ok` are
    explicit parameters rather than derived inside this function, because
    none of them is recoverable from `ActionProposal`, `Cart`, or
    `ConsentRecord` alone -- the caller (the Write Guard node) is the one
    place that has all four."""
    canonical_args = proposal.canonical_args

    if proposal.tool_name not in WRITE_TOOL_ALLOWLIST:
        return WriteDecision(
            authorized=False,
            reason=f"tool '{proposal.tool_name}' is not on the write allowlist",
            canonical_args=canonical_args,
        )
    if proposal.tool_name in GUEST_ONLY_ACTIONS:
        return WriteDecision(
            authorized=False,
            reason=f"'{proposal.tool_name}' is a guest-only action",
            canonical_args=canonical_args,
        )
    if proposal.tool_name in quarantined:
        return WriteDecision(
            authorized=False,
            reason=f"tool '{proposal.tool_name}' is quarantined pending review",
            canonical_args=canonical_args,
        )
    if live_tool_hash != reviewed_tool_hash:
        return WriteDecision(
            authorized=False,
            reason="live tool schema hash does not match the reviewed baseline",
            canonical_args=canonical_args,
        )
    if consent_expired:
        return WriteDecision(
            authorized=False,
            reason="consent has expired",
            canonical_args=canonical_args,
        )
    if consent.consumed_at is not None:
        return WriteDecision(
            authorized=False,
            reason="consent has already been consumed",
            canonical_args=canonical_args,
        )
    if consent.action_id != proposal.action_id:
        return WriteDecision(
            authorized=False, reason="action_id mismatch", canonical_args=canonical_args
        )
    if consent.owner != owner:
        return WriteDecision(
            authorized=False, reason="owner mismatch", canonical_args=canonical_args
        )
    if consent.session_id != session_id:
        return WriteDecision(
            authorized=False,
            reason="session_id mismatch",
            canonical_args=canonical_args,
        )
    if canonical_args.get("shoppingCartId") != re_read_cart.cart_id:
        return WriteDecision(
            authorized=False,
            reason="cart id changed since consent was granted",
            canonical_args=canonical_args,
        )

    if consent.args_hash != compute_args_hash(canonical_args):
        return WriteDecision(
            authorized=False, reason="args_hash mismatch", canonical_args=canonical_args
        )
    if consent.state_hash != compute_state_hash(re_read_cart):
        return WriteDecision(
            authorized=False,
            reason="state_hash mismatch",
            canonical_args=canonical_args,
        )

    shape_errors = _canonical_args_shape_errors(canonical_args)
    if shape_errors:
        return WriteDecision(
            authorized=False,
            reason="; ".join(shape_errors),
            canonical_args=canonical_args,
        )

    if not budget_reserve_ok:
        return WriteDecision(
            authorized=False,
            reason="insufficient budget reserve for the mandatory read-back",
            canonical_args=canonical_args,
        )

    return WriteDecision(authorized=True, reason="", canonical_args=canonical_args)


def finalize_write_outcome(
    mcp_write_response: dict[str, Any],
    read_back_result: Optional[Cart],
    *,
    before: Cart,
    expected_delta: Money,
    expected_product_id: str,
    expected_quantity: Decimal,
) -> WriteOutcome:
    """`mcp_write_response["success"]` is recorded nowhere in this
    function's decision -- the tool's own schema documents it as proof
    only that the request was accepted (plan section 11, DR-12). The
    only thing that can produce `status="receipt"` is an independent
    read-back whose diff matches the consented action by *identity*, not
    merely by total (D-G5-19): a coincidentally equal total from an
    unrelated concurrent change is `unverified`, not a receipt.
    """
    del mcp_write_response  # deliberately unused -- see the docstring above

    if read_back_result is None:
        return WriteOutcome(
            status="unverified",
            reason="read-back unreachable",
            diff=None,
            actual_delta=None,
        )

    try:
        diff = canonical_diff(before, read_back_result)
    except ValueError as exc:
        # D-G5-19b: measured (M6) that this invariant holds on ordinary
        # traffic -- it raises exactly when the cart changed concurrently
        # with this write, which is the case that must be reported as
        # `unverified`, never allowed to escape as an exception that skips
        # `mark_action` and leaves the idempotency row stuck `in_flight`.
        return WriteOutcome(
            status="unverified", reason=str(exc), diff=None, actual_delta=None
        )

    if diff.removed:
        return WriteOutcome(
            status="unverified",
            reason="read-back shows removed line items, none were consented",
            diff=diff,
            actual_delta=diff.total_delta,
        )

    matched = [item for item in diff.added if item.product_id == expected_product_id]
    matched += [
        after
        for _before, after in diff.changed
        if after.product_id == expected_product_id
    ]
    other_changes = [
        item for item in diff.added if item.product_id != expected_product_id
    ]
    other_changes += [
        after
        for _before, after in diff.changed
        if after.product_id != expected_product_id
    ]

    if len(matched) != 1 or other_changes:
        return WriteOutcome(
            status="unverified",
            reason="read-back diff does not match the consented product by identity",
            diff=diff,
            actual_delta=diff.total_delta,
        )

    if matched[0].quantity != expected_quantity:
        return WriteOutcome(
            status="unverified",
            reason="read-back quantity does not match the consented quantity",
            diff=diff,
            actual_delta=diff.total_delta,
        )

    # A differing total is NOT a verification failure. The identity checks
    # above already established that exactly the consented product landed,
    # at the consented quantity, with nothing else moved -- the cart is in
    # the intended state. A different total means the price ESTIMATE was
    # wrong, which is a fact about our own arithmetic, not about the write.
    #
    # Measured on the first live write: `find_products_batch` reported 9.34
    # for a product the cart then priced at 8.41 (exactly 10% lower, with
    # `oldPrice` null -- the search endpoint does not expose that discount
    # at all). Gating the receipt on equality made every discounted product
    # permanently unverifiable, and left `CostDeltaAccuracy` -- the plan
    # section 13 metric whose entire job is measuring this difference --
    # with nothing to measure, since a mismatch could never reach a receipt.
    delta_note = (
        ""
        if diff.total_delta == expected_delta
        else (
            f"cart applied a different price than the search result: "
            f"expected {expected_delta}, actual {diff.total_delta}"
        )
    )

    new_error_validations = [
        v
        for v in read_back_result.validations
        if v.level == "error" and v.context.get("productId") == expected_product_id
    ]
    if new_error_validations:
        return WriteOutcome(
            status="unverified",
            reason=(
                "read-back cart carries a new error-level validation for the "
                "written product"
            ),
            diff=diff,
            actual_delta=diff.total_delta,
        )

    return WriteOutcome(
        status="receipt", reason=delta_note, diff=diff, actual_delta=diff.total_delta
    )
