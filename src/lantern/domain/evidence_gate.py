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

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from src.lantern.domain.models import EvidenceTuple, Money


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
    """

    call_id: str
    source_tool: str
    external_product_id: Optional[int]
    slug: str
    name: str
    price_raw: Any  # exactly what the tool's JSON carried — unconverted
    available_raw: Any
    captured_at: datetime


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
                )
            )
    return candidates


def resolve_product_id(raw: RawCandidate) -> Optional[str]:
    """Match by `externalProductId` (the article code) when
    present; fall back to `slug` when it is null (the tool's own
    `outputSchema` types this field `number | null` — measured, not
    assumed). A candidate with neither is `unresolved` — dropped, never
    guessed at."""
    if raw.external_product_id is not None:
        return str(raw.external_product_id)
    if raw.slug:
        return raw.slug
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

    (a) its product id resolves (externalProductId, falling back to slug);
        a candidate resolving to neither is dropped, not guessed;
    (b) its price converts to a positive `Money` (`_resolve_price` above) —
        a present-but-invalid value (a string that isn't a number, zero, or
        negative) is rejected here, not merely a missing one — a
        well-formed JSON carrying a false value, not an absent field;
    (c) `available_raw is True` exactly — not merely truthy, so a stray
        `1`/`"true"` from a malformed upstream response does not silently
        pass as a boolean `True` the way Python's own truthiness would.

    Every survivor is built through `EvidenceTuple`'s normal Pydantic
    constructor, never `model_construct` — that is what keeps the Money
    conversion guarantee in force (see `_resolve_price`'s docstring).
    """
    survivors: list[EvidenceTuple] = []
    for raw in raw_candidates:
        product_id = resolve_product_id(raw)
        if product_id is None:
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
