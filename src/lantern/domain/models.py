"""Domain Core models: Cart, Validation,
Blocker, Diagnosis, EvidenceTuple, CartDiff, ActionProposal, ConsentRecord,
Receipt. Pure Pydantic — no I/O, matching this project's layering rule
(`tests/unit/test_layering.py`, `domain` may only import `kernel`).

`PolicyEntry` lives here rather than in `src/lantern/policies/loader.py`: a
cross-module forward reference from `Blocker.policy` to a type defined in a
sibling module raised `PydanticUserError` at construction time, and the
naive fix (importing the sibling module) produced a real `ImportError` from
a circular import once `diagnosis.py` needed `Cart`/`Diagnosis` back. Both
`models` and `policies` are layer `domain`, so keeping the type here costs
nothing architecturally and removes the cycle entirely.

`Gap` (the `Decimal` subclass diagnosis.py returns) never appears as a field
type on any model here: a bare `Decimal`
subclass has no `__get_pydantic_core_schema__`, so Pydantic cannot build a
schema for it (`PydanticSchemaGenerationError`), and even a working subclass
loses its own subtype identity under ordinary arithmetic (`g + Decimal("1")`
returns a plain `Decimal`). `Diagnosis.gap` is therefore a plain `Decimal`
plus a separate `gap_is_borderline: bool`, set once at construction from the
`Gap` value `diagnosis.py` computed and then discarded.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

Money = Decimal

# Checkout, payment, and age confirmation stay the guest's own actions —
# no `ActionProposal` may ever name one of these as its `tool_name`. A
# frozenset, not a comment, so the rule has an artefact a test can check
# against (`tests/unit/test_dr_13_guest_only_actions.py`) rather than only
# living in prose that a future edit can silently violate.
GUEST_ONLY_ACTIONS: frozenset[str] = frozenset(
    {
        "silpo_checkout",
        "silpo_confirm_age",
        "silpo_pay_order",
    }
)


class PolicyEntry(BaseModel):
    """One row of the policy registry: validation code -> rule, source,
    version, test_id, confidence. `status` distinguishes live-observed-but-
    unregistered codes (`quarantined`) from confirmed ones (`active`) — a
    quarantined entry is never used to authorize anything, only to
    disclose that the code is known but not yet reviewed."""

    model_config = ConfigDict(frozen=True)

    code: str
    rule: str
    source: str
    version: str
    test_id: str
    confidence: Literal["confirmed", "unconfirmed"]
    status: Literal["active", "quarantined"] = "active"


class Validation(BaseModel):
    """One entry of a cart's `calculation.validations` array. `code` is
    populated from the wire field `message` — the live payload has no
    `code` field at all — by `normalizer.py`, the one place this
    rename happens.
    """

    model_config = ConfigDict(frozen=True)

    level: Literal["error", "warning", "info"]
    type: str
    code: str
    context: dict[str, Any] = {}


class LineItem(BaseModel):
    """One product line under a cart shipment
    (`cart.shipments[].products[]` on the live wire shape, measured
    2026-09-06). `company_id`/`branch_id` are
    optional and carried per-item rather than assumed from a single
    shipment, because a multi-shipment cart splitting across branches is
    unmeasured (only a one-shipment cart has been captured so far)."""

    model_config = ConfigDict(frozen=True)

    product_id: str
    name: str
    quantity: Decimal
    price: Money
    stock: Optional[int] = None
    sub_discount: Optional[Money] = None
    company_id: Optional[str] = None
    branch_id: Optional[str] = None


class Cart(BaseModel):
    """`extra="allow"`: unknown fields are kept but are
    never trusted as write arguments — only the Write Guard's own
    allowlisted, explicitly-typed arguments authorize a write."""

    model_config = ConfigDict(extra="allow", frozen=True)

    cart_id: str
    branch_id: Optional[str] = None
    company_id: Optional[str] = None
    delivery_type: Optional[str] = None
    products_total: Money
    total: Optional[Money] = None
    total_after_discounts: Optional[Money] = None
    sub_total: Optional[Money] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timeslot_start: Optional[datetime] = None
    timeslot_end: Optional[datetime] = None
    validations: list[Validation] = []
    products: list[LineItem] = []
    min_order_cost: Optional[Money] = None
    delivery_cost: Optional[Money] = None
    restrictions: list[str] = []
    constraints: dict[str, bool] = {}
    # G5+G6 (D-G5-25): the requirements checklist requires the ABSENCE of
    # this field to be treated as an additional signal, never as a plain
    # equivalence to "blocked" -- the tool's own schema documents it as
    # present "when cart is non-empty and error-free", so a missing link
    # can mean either a real blocker or simply an empty cart.
    checkout_web_link: Optional[str] = None


class Blocker(BaseModel):
    """A validation the diagnosis has classified as blocking (error or
    allowlisted warning). `product_ref` is the validation's own
    `productId` when one exists and resolves against `Cart.products`, or
    the literal string `"unresolved"` when the id is absent or dangling —
    never `None`, so a renderer never has to special-case a
    missing value versus one that failed to resolve."""

    model_config = ConfigDict(frozen=True)

    validation: Validation
    policy: Optional[PolicyEntry]
    is_known: bool
    product_ref: str


class Diagnosis(BaseModel):
    """`gap` is a plain `Decimal`, never the `Gap` subclass `diagnosis.py`
    computes internally (see the module docstring above)."""

    model_config = ConfigDict(frozen=True)

    blockers: list[Blocker]
    disclosures: list[Validation]
    gap: Optional[Money]
    gap_is_borderline: bool
    primary_code: Optional[str]
    threshold_source: Literal["validation_context", "time_slots", "unverified"]


class LineItemClassification(BaseModel):
    """Whether a line item is a genuine candidate. `is_available`
    is never set from `price == 0` alone — see `diagnosis.classify_line_item`."""

    model_config = ConfigDict(frozen=True)

    is_available: bool
    reason: str


class EvidenceTuple(BaseModel):
    """Evidence Gate input shape: all four fields are required and
    non-optional by construction, so an incomplete evidence tuple cannot
    be built at all — the gate logic is a separate concern, but the shape
    that makes "no evidence" unrepresentable belongs here."""

    model_config = ConfigDict(frozen=True)

    product_id: str
    price: Money
    availability: bool
    source_tool: str
    captured_at: datetime


class CartDiff(BaseModel):
    """Canonical before/after diff."""

    model_config = ConfigDict(frozen=True)

    added: list[LineItem]
    removed: list[LineItem]
    changed: list[tuple[LineItem, LineItem]]
    total_delta: Money


class ActionProposal(BaseModel):
    """The consent sentence — "Додати товар X, кількість Y,
    очікувана сума Z" — needs a name and quantity typed on the model
    itself, not buried inside `canonical_args`; `product_name`/`quantity`
    are X and Y, `expected_delta` is Z. `canonical_args` stays a dict for
    forward compatibility with tools beyond the hero write, but its key
    set is pinned for the one tool exercised so far (G5+G6, D-G5-02): the
    complete, exact `silpo_add_or_update_cart_products` argument object --
    `{shoppingCartId: str, products: [{productId, companyId, branchId:
    str, quantity: number, addQuantity: bool}]}` -- byte-for-byte what the
    Write Guard sends, since `args_hash` binds consent to this object and
    a hash over a summary of the call proves nothing about the call
    itself. `addQuantity` is always `False` (replace, not add) and
    explicit, never left to a default."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    tool_name: str
    product_name: str
    quantity: Decimal
    expected_delta: Money
    canonical_args: dict[str, Any]
    evidence: list[EvidenceTuple]
    # The explainer node's own rendered UA sentence for the
    # consent screen — empty until `explain` runs, attached via
    # `model_copy(update=...)` since this model is frozen. Default keeps
    # every existing construction site unbroken.
    guest_text_uk: str = ""


class ConsentRecord(BaseModel):
    """Mirrors `0003_consents.sql` + `0006_consent_receipt_versioning.sql`
    column for column. `cart_id`/`prompt_version`/`policy_version` were
    added at G5+G6 (D-G5-09): plan section 11 requires a consent bound to
    the specific cart and the prompt/policy version that produced it, and
    `state_hash` deliberately excludes cart identity (it hashes contents,
    not identity), so `cart_id` has to live here explicitly. `owner` is
    the migration's column name, kept rather than `user_id_hash`."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    session_id: str
    owner: str
    cart_id: str
    canonical_args: dict[str, Any]
    args_hash: str
    state_hash: str
    prompt_version: Optional[str] = None
    policy_version: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    consumed_at: Optional[datetime] = None


class Receipt(BaseModel):
    """Mirrors `0005_receipts.sql` + `0006_consent_receipt_versioning.sql`.
    `status`/`reason`/`expected_delta`/`actual_delta`/`trace_id` were added
    at G5+G6 (D-G5-09): plan section 13.3's metrics need "read-back
    attempted" separated from "verification succeeded", a stored
    expectation to compare a delta against, and a way to join a receipt
    back to its own LangSmith trace — none of which `verified: bool` alone
    can carry. `verified` stays for existing callers and is derived from
    `status`."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    session_id: str
    owner: str
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    verified: bool
    status: Literal["receipt", "unverified"]
    reason: str
    expected_delta: Optional[Money] = None
    actual_delta: Optional[Money] = None
    trace_id: Optional[str] = None
    created_at: datetime
