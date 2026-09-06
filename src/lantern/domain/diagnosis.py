"""DR-03, DR-04, DR-06, DR-07, DR-08, DR-09, DR-11: gap arithmetic, the
surcharge label, blocker classification and dedupe, and the canonical
before/after diff. Pure code — DR-09's own rule ("Gap і totals обчислює
код; LLM лише пояснює і ранжує") means nothing here ever takes a
pre-computed total or gap as an input argument; every number is derived
from a `Cart`.
"""

from decimal import Decimal
from typing import Iterable, Literal, Mapping, Optional, Sequence

from src.lantern.domain.models import (
    Blocker,
    Cart,
    CartDiff,
    Diagnosis,
    LineItem,
    LineItemClassification,
    Money,
    Validation,
)
from src.lantern.domain.normalizer import to_money
from src.lantern.policies.loader import PolicyRegistry

# D-G3-10 (amended): a declared POLICY CONSTANT, not a measured value.
# The only thing actually established is that the declared test needs
# epsilon > 0.01; 1.00 was the author's choice at kickoff. What would
# calibrate it: the minimum observed product price from a live
# `silpo_find_products_batch` sweep (blocked on the OAuth login same as
# every other live measurement — see this stage's risk R7).
# ponytail: policy constant pending calibration against a live price floor.
GAP_EPSILON = Decimal("1.00")

# DR-06: blockers are error-level or an allowlisted warning; info never
# blocks (G3-F3).
_BLOCKING_LEVELS = {"error", "warning"}

# DR-04: the only UI-confirmed surcharge label (plan section 10 — the 9 UAH
# self-pickup service fee). Every other channel gets the neutral wording.
_SERVICE_FEE_DELIVERY_TYPE = "SelfPickup"


class Gap(Decimal):
    """DR-03's gap value. A return type only — never stored as a model
    field and never assigned to a variable that outlives its own
    construction call, because arithmetic on a `Decimal` subclass returns
    a plain `Decimal` and silently drops any extra attribute (measured:
    `g + Decimal("1")` -> `Decimal`,
    `type(...)` is `Decimal`, not `Gap`). Callers read `.is_borderline`
    immediately and unpack both values onto `Diagnosis` (`gap`,
    `gap_is_borderline`) rather than keeping a `Gap` alive.
    """

    __slots__ = ("is_borderline",)
    is_borderline: bool

    def __new__(cls, value: Decimal, *, is_borderline: bool) -> "Gap":
        self = super().__new__(cls, value)
        object.__setattr__(self, "is_borderline", is_borderline)
        return self


def compute_order_cost_min_gap(min_order_cost: Money, products_total: Money) -> Gap:
    """DR-03: gap = minOrderCost - productsTotal, never against `total` or
    `totalAfterDiscounts` (amendment A2 — a units-confusion bug, not a
    server inconsistency, but the fail-closed comparison stays cheap
    defense-in-depth). A gap under `GAP_EPSILON` reads as borderline,
    never an automatic pass."""
    raw = min_order_cost - products_total
    return Gap(raw, is_borderline=Decimal(0) < raw < GAP_EPSILON)


def compute_surcharge(
    total: Money, products_total: Money, delivery_type: str
) -> tuple[Money, Literal["service_fee", "difference"]]:
    """DR-04: surcharge = total - productsTotal. Labelled "service fee"
    only for SelfPickup, the one channel plan section 10 records as
    UI-confirmed (9 UAH); every other channel gets neutral wording so an
    unconfirmed number is never presented as an official fee."""
    amount = total - products_total
    label: Literal["service_fee", "difference"] = (
        "service_fee" if delivery_type == _SERVICE_FEE_DELIVERY_TYPE else "difference"
    )
    return amount, label


def classify_line_item(
    price: Money, stock: Optional[int], error_code: Optional[str]
) -> LineItemClassification:
    """DR-08: `price == 0` alone never decides availability — the prior
    hypothesis that unavailable items are excluded from the sum was
    disproven on live data (`[I5]` section 13.1). Availability needs an
    explicit signal: a known error code, or a positive stock count."""
    if error_code is not None:
        return LineItemClassification(is_available=False, reason=error_code)
    if stock is not None and stock <= 0:
        return LineItemClassification(is_available=False, reason="out_of_stock")
    return LineItemClassification(is_available=True, reason="in_stock")


def sum_line_items(line_items: Iterable[Mapping[str, object]]) -> Money:
    """DR-08: Sigma(price * quantity) == productsTotal, including
    zero-priced (unavailable) items — they are not excluded from the sum
    on the live server (`[I6]` section 2). `quantity` is read explicitly
    so an implementation cannot pass by accident on a fixture where every
    quantity happens to be 1 (G3-F4b)."""
    total = Decimal("0")
    for item in line_items:
        price = item["price"]
        quantity = item.get("quantity", 1)
        # `assert` would be stripped under `python -O`, silently turning a
        # money-type violation into a `float`-arithmetic bug (G3-F6) instead
        # of a loud failure — raised explicitly so the invariant survives
        # optimization.
        if not isinstance(price, Decimal):
            raise TypeError(
                f"sum_line_items requires Decimal prices, got {type(price).__name__}"
            )
        total += price * Decimal(str(quantity))
    return total


def _resolve_product_ref(
    product_id: Optional[str], products: Sequence[LineItem]
) -> str:
    """G3-F19: a validation's `productId` that matches no line item in the
    cart becomes the explicit string "unresolved" — never `None`, and
    never a crash from a renderer that assumes every blocker resolves to
    a real product."""
    if product_id is None:
        return "unresolved"
    if any(p.product_id == product_id for p in products):
        return product_id
    return "unresolved"


def _dedupe_key(validation: Validation) -> str:
    """DR-07: dedupe groups by `productId` alone when present — the
    priority rule ("not_found outranks stock.max") only makes sense
    across *different* codes describing the *same* product, so grouping
    by `(code, productId)` instead (an earlier, wrong draft of this
    function) would put `stock.max` and `not_found` in separate groups by
    construction and the priority would never fire.

    A validation without a `productId` (both live order-level codes
    observed so far carry none) is its own unmergeable group — merging
    two unrelated order-level blockers would hide one of them (G3-F10)."""
    product_id = validation.context.get("productId")
    if product_id is None:
        return f"__no_product_id__:{id(validation)}"
    return str(product_id)


_NOT_FOUND_CODE = "product.offer.not_found"
_STOCK_MAX_CODE = "product.offer.stock.max"


def diagnose(cart: Cart, registry: PolicyRegistry) -> Diagnosis:
    """DR-06/07/09: the deterministic diagnosis. Never accepts a
    pre-computed total or gap as an argument (DR-09) — every number comes
    from `cart` itself."""
    blockers: list[Blocker] = []
    disclosures: list[Validation] = []

    # DR-07: group by productId (see _dedupe_key's docstring for why not
    # (code, productId)) — within a group, not_found outranks stock_max.
    grouped: dict[str, list[Validation]] = {}
    for validation in cart.validations:
        key = _dedupe_key(validation)
        grouped.setdefault(key, []).append(validation)

    for group in grouped.values():
        representative = group[0]
        if len(group) > 1:
            not_found = [v for v in group if v.code == _NOT_FOUND_CODE]
            if not_found:
                representative = not_found[0]
            else:
                stock_max = [v for v in group if v.code == _STOCK_MAX_CODE]
                if stock_max:
                    representative = stock_max[0]

        if representative.level not in _BLOCKING_LEVELS:
            disclosures.append(representative)
            continue

        policy = registry.lookup(representative.code)
        is_known = policy is not None and policy.status == "active"
        product_id = representative.context.get("productId")
        blockers.append(
            Blocker(
                validation=representative,
                policy=policy,
                is_known=is_known,
                product_ref=_resolve_product_ref(product_id, cart.products),
            )
        )

    gap: Optional[Money] = None
    gap_is_borderline = False
    primary_code: Optional[str] = None
    threshold_source: Literal["validation_context", "time_slots", "unverified"] = (
        "validation_context"
    )

    cost_min_blocker = next(
        (b for b in blockers if b.validation.code == "order.cost.min"), None
    )
    if cost_min_blocker is not None:
        primary_code = "order.cost.min"
        context_threshold = cost_min_blocker.validation.context.get("orderCostMin")
        slot_threshold = cart.min_order_cost

        if context_threshold is not None:
            threshold = to_money(context_threshold)
            threshold_source = "validation_context"
        elif slot_threshold is not None:
            threshold = slot_threshold
            threshold_source = "time_slots"
        else:
            threshold = None
            threshold_source = "unverified"

        if threshold is not None:
            computed = compute_order_cost_min_gap(threshold, cart.products_total)
            gap = Decimal(computed)
            gap_is_borderline = computed.is_borderline

    return Diagnosis(
        blockers=blockers,
        disclosures=disclosures,
        gap=gap,
        gap_is_borderline=gap_is_borderline,
        primary_code=primary_code,
        threshold_source=threshold_source,
    )


def canonical_diff(before: Cart, after: Cart) -> CartDiff:
    """DR-11: the canonical before/after diff. Asserts its own totals
    invariant internally (G3-F13) — a diff that silently understates the
    real delta raises rather than returning a wrong-but-plausible value."""
    before_by_id = {p.product_id: p for p in before.products}
    after_by_id = {p.product_id: p for p in after.products}

    added = [p for pid, p in after_by_id.items() if pid not in before_by_id]
    removed = [p for pid, p in before_by_id.items() if pid not in after_by_id]
    changed = [
        (before_by_id[pid], after_by_id[pid])
        for pid in before_by_id.keys() & after_by_id.keys()
        if before_by_id[pid].quantity != after_by_id[pid].quantity
        or before_by_id[pid].price != after_by_id[pid].price
    ]

    total_delta = after.products_total - before.products_total

    expected_delta = (
        sum((p.price * p.quantity for p in added), Decimal("0"))
        - sum((p.price * p.quantity for p in removed), Decimal("0"))
        + sum(
            (
                (after_item.price * after_item.quantity)
                - (before_item.price * before_item.quantity)
                for before_item, after_item in changed
            ),
            Decimal("0"),
        )
    )
    if expected_delta != total_delta:
        raise ValueError(
            f"canonical_diff invariant violated: line-item delta {expected_delta} "
            f"!= productsTotal delta {total_delta}"
        )

    return CartDiff(
        added=added, removed=removed, changed=changed, total_delta=total_delta
    )


__all__ = [
    "GAP_EPSILON",
    "Gap",
    "compute_order_cost_min_gap",
    "compute_surcharge",
    "classify_line_item",
    "sum_line_items",
    "diagnose",
    "canonical_diff",
]
