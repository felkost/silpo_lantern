"""The Evidence Gate: the deterministic filter between "the planner said
look for X" and "an ActionProposal exists." No candidate reaches
`rank`/`explain` without a live, type-and-range-valid `EvidenceTuple`
built from an actual `silpo_find_products_batch` response — never from
the planner's own structured output, which has no field this module's
constructor reads (the LLM never supplies a price, an availability flag,
or a productId that becomes evidence).

Pure per this project's "domain core does no I/O" invariant: everything
here operates on data the caller already fetched.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from src.lantern.domain.models import EvidenceTuple, Money

# live probe P1 confirmed `find_products_batch`'s own
# `id`/`companyId`/`branchId` are UUID-shaped, matching the same pattern
# `tests/contract/fixtures/tools_list_2026-09-05.json`'s write tool
# requires -- checked here, not merely presence, so a malformed non-UUID
# string cannot slip through as if it could ever be sent to the write tool.
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _is_uuid_shaped(value: Optional[str]) -> bool:
    return value is not None and bool(_UUID_RE.match(value))


@dataclass(frozen=True)
class RawCandidate:
    """One product row from one `silpo_find_products_batch` call, tagged
    with that call's own id. `call_id` is what makes provenance structural
    rather than merely conventional: the
    planner's structured-output type has no field shaped like this and no
    path that constructs one — a hallucinated evidence tuple would have to
    forge an entire `RawCandidate`, not just supply four convincing-looking
    values, and nothing in this module accepts one from anywhere but
    `raw_candidates_from_find_products_batch`.

    `product_uuid`/`company_id`/`branch_id`/`stock`/`weighted`/`step`
    are the write tool's own argument fields, confirmed
    live (probe P1) to be the catalogue product's real UUID -- the SAME
    identifier the cart's own `LineItem.product_id` carries for a product
    already in the cart, not a fourth, separate space. `external_product_id`
    stays a distinct field: an earlier decision already settled that it is structurally
    incompatible with the cart's own id, and `channel_snapshot_builder`
    still matches on it for its own, unrelated purpose (item availability
    per channel).
    """

    call_id: str
    source_tool: str
    external_product_id: Optional[int]
    slug: str
    name: str
    price_raw: Any  # exactly what the tool's JSON carried — unconverted
    available_raw: Any
    captured_at: datetime
    product_uuid: Optional[str] = None
    company_id: Optional[str] = None
    branch_id: Optional[str] = None
    stock: Optional[int] = None
    weighted: Optional[bool] = None
    step: Optional[Decimal] = None


def raw_candidates_from_find_products_batch(
    call_id: str,
    response: Mapping[str, Any],
    captured_at: datetime,
) -> list[RawCandidate]:
    """The only constructor for `RawCandidate`. Walks the real
    `find_products_batch` response shape (`queries[].products[]`, measured
    directly from the tracked contract fixture's `outputSchema`), not a
    paraphrase of it. Never called with planner output —
    `collect_options` (the graph node, not yet
    built) is this function's only intended caller.
    """
    candidates: list[RawCandidate] = []
    for query in response.get("queries", []):
        for product in query.get("products", []):
            step_raw = product.get("step")
            candidates.append(
                RawCandidate(
                    call_id=call_id,
                    source_tool="silpo_find_products_batch",
                    external_product_id=product.get("externalProductId"),
                    slug=product.get("slug", ""),
                    name=product.get("name", ""),
                    price_raw=product.get("price"),
                    available_raw=product.get("available"),
                    captured_at=captured_at,
                    product_uuid=product.get("id"),
                    company_id=product.get("companyId"),
                    branch_id=product.get("branchId"),
                    stock=product.get("stock"),
                    weighted=product.get("weighted"),
                    step=Decimal(str(step_raw)) if step_raw is not None else None,
                )
            )
    return candidates


def resolve_product_id(raw: RawCandidate) -> Optional[str]:
    """resolves to `product_uuid` -- the catalogue
    product's own UUID, confirmed live (probe P1) to be the exact
    identifier the write tool's `productId` argument expects, and to
    match the cart's own `LineItem.product_id` when the product is
    already in the cart. Retires the `externalProductId`/`slug` fallback
    this function used before that measurement existed: `id` is a
    required, non-null field in the tool's own `outputSchema`, so a
    resolved evidence tuple can now always be turned into a real write
    argument, not merely a plausible-looking one. A candidate with no
    `product_uuid` is `unresolved` — dropped, never guessed at.
    """
    if raw.product_uuid:
        return raw.product_uuid
    return None


def _resolve_price(raw: RawCandidate) -> Optional[Money]:
    """Constructs the `EvidenceTuple` through Pydantic validation rather
    than assigning a converted value onto an already-built model — measured
    (`test_evidence_gate_price_via_pydantic_decimal_path.py`) to route a raw
    JSON float through the same `Decimal(str(value))` path `to_money` uses,
    not `Decimal(value)` directly. Returns `None` on anything that fails to
    parse into a positive `Money`, which the caller drops rather than
    raises — a malformed candidate is absence of evidence, not a crash."""
    try:
        price = Money(str(raw.price_raw))
    except (TypeError, ValueError, ArithmeticError):
        return None
    if price <= 0:
        return None
    return price


def gate_candidates(raw_candidates: Sequence[RawCandidate]) -> list[EvidenceTuple]:
    """A candidate survives only if:

    (a) its product id resolves to a UUID-shaped `product_uuid`, and its
        `company_id`/`branch_id` are also UUID-shaped —
        the three arguments the write tool's own `inputSchema` requires
        per product. A candidate missing any of the three could be shown
        to the guest but never actually written, which is exactly the
        promise this gate already makes for price/availability;
    (b) its price converts to a positive `Money` (`_resolve_price` above) —
        a present-but-invalid value (a string that isn't a number, zero, or
        negative) is rejected here, not merely a missing one — a
        well-formed JSON carrying a false value, not an absent field;
    (c) `available_raw is True` exactly — not merely truthy, so a stray
        `1`/`"true"` from a malformed upstream response does not silently
        pass as a boolean `True` the way Python's own truthiness would.

    Stock/weighted-step validity is deliberately NOT checked here: it
    depends on the requested quantity, which this gate does not know yet
    — `action_proposal_builder.build_action_proposals` checks it once the
    quantity is available.

    Every survivor is built through `EvidenceTuple`'s normal Pydantic
    constructor, never `model_construct` — that is what keeps the Money
    conversion guarantee in force (see `_resolve_price`'s docstring).
    """
    survivors: list[EvidenceTuple] = []
    for raw in raw_candidates:
        product_id = resolve_product_id(raw)
        if product_id is None or not _is_uuid_shaped(product_id):
            continue
        if not _is_uuid_shaped(raw.company_id) or not _is_uuid_shaped(raw.branch_id):
            continue
        price = _resolve_price(raw)
        if price is None:
            continue
        if raw.available_raw is not True:
            continue
        survivors.append(
            EvidenceTuple(
                product_id=product_id,
                price=price,
                availability=True,
                source_tool=raw.source_tool,
                captured_at=raw.captured_at,
            )
        )
    return survivors
