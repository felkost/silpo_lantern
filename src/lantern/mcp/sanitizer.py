"""Allow-list based fixture sanitization — anything not explicitly reviewed
is dropped, never passed through by default. `scripts/sanitize_fixture.py`
is the thin CLI wrapper that reads a raw captured payload, calls
`sanitize_payload`, and writes the result into
`datasets/fixtures/sanitized/`.

The field list below is a first cut from documented cart-snapshot fields
(`notebooks/evidence_lab.ipynb`) for non-PII, product/pricing-level data. It
is not a claim of completeness for every field the live server can return —
every sanitized fixture still needs a human review pass before commit: does
an allowed field's *value* look like free text that could carry PII.
"""

import re
from typing import Any, Dict, Optional

# Product/pricing-level fields only — no address, contact, or free-text
# fields. Extend this list only after reviewing what a real capture
# actually contains, never by guessing what "seems safe".
#
# Widened 2026-09-06 against the real `silpo_get_shopping_cart_by_id` wire
# shape — the original list was built from the evidence notebook's own
# *flattened* view (`productsTotal`, `deliveryType` at the top level) and
# did not include the structural nesting keys (`cart`, `calculation`,
# `shipments`) the raw wire response actually uses, so sanitizing a real
# capture silently produced an empty payload. `address` is deliberately
# never added — it carries exact coordinates and a street address, which
# must be removed, not allowed.
ALLOWED_KEYS = frozenset(
    {
        "productId",
        "companyId",
        "branchId",
        "name",
        "slug",
        "price",
        "oldPrice",
        "subDiscount",
        "subTotal",
        "quantity",
        "stock",
        "weighted",
        "productsTotal",
        "total",
        "totalAfterDiscounts",
        "deliveryType",
        "minOrderCost",
        "deliveryCost",
        "products",
        "validations",
        "level",
        "type",
        "message",
        "code",
        "context",
        # structural nesting keys — the raw wire shape, not the notebook's
        # flattened one
        "cart",
        "calculation",
        "shipments",
        "delivery",
        "timeslot",
        "start",
        "end",
        "payment",
        "availableTypes",
        # `silpo_get_my_shopping_cart`'s own (very small) response shape —
        # it returns no cart body at all, which is a contract fact worth
        # pinning in a fixture rather than rediscovering
        "success",
        "exists",
        "shoppingCartId",
        # widened for `find_products_batch`/`time_slots`/
        # `delivery_types`/the write response — sanitizing any of these
        # with the earlier list silently produced `{}` (the same failure
        # mode this file's own 2026-09-06 note already records for the
        # cart shape). `queries`/`query` (search echo), `step`/`available`/
        # `externalProductId` (find_products_batch's own product shape),
        # `slots`/`deliveryCostMap` (time_slots), `options` (delivery_types),
        # `summary` (the write response's `{success, summary, products}`).
        # `id` is here for the same reason `productId`/`shoppingCartId`
        # already are — kept only so it can reach the pseudonymisation
        # step in `_PSEUDONYMISED_KEYS` below, never passed through raw.
        "id",
        "queries",
        "query",
        "step",
        "available",
        "externalProductId",
        "slots",
        "deliveryCostMap",
        "options",
        "summary",
        # `deliveryCostMap` was allow-listed but the keys INSIDE each
        # of its entries were not, so every entry sanitized to `{}` and
        # `channel_snapshot_builder._money_map_entry` then read `None`
        # for two required Decimal fields -- the replayed
        # `compare_channels` node raised on it. Same failure shape this
        # file's own 2026-09-06 and earlier notes already record twice: a
        # container key allowed without its contents produces an empty
        # object rather than a loud error. Both are pricing figures, no
        # PII.
        "cost",
        "fromOrderCost",
    }
)


# Keys whose *values* are stable identifiers tying a fixture back to a real
# account, branch or catalogue entry. These must be replaced with local
# `test_*` values, keeping referential integrity — dropping them would break
# the references between a validation's `productId` and the line item it
# points at, and passing them through would publish real ids. They are
# pseudonymised instead, with one stable mapping per sanitize run so every
# reference to the same original id lands on the same replacement.
_PSEUDONYMISED_KEYS = {
    "productId": "test_product",
    "companyId": "test_company",
    "branchId": "test_branch",
    "cartId": "test_cart",
    "shoppingCartId": "test_cart",
    # `id` is a bare identifier used across several response
    # shapes (cart id, shipment id, a find_products_batch product's own
    # id) -- pseudonymised like the others, never allow-listed raw. The
    # alias map is keyed by VALUE, so an `id` that happens to equal a
    # `shoppingCartId`/`productId` value elsewhere in the same payload
    # lands on the same replacement automatically.
    "id": "test_id",
}

# `context` is a free-form object the server fills as it likes, so it is not
# allow-listed wholesale. These are the keys measured in real captures, and
# `orderCostMin` in particular is load-bearing: without it a fixture cannot
# exercise the minimum-order-cost gap check at all.
_ALLOWED_CONTEXT_KEYS = frozenset(
    {
        "orderCostMin",
        "productId",
        "reason",
        "paymentTypes",
        "total",
        "minTotal",
    }
)


def sanitize_payload(
    raw: Dict[str, Any], aliases: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Keeps only allow-listed keys, recursing into nested dicts and lists
    of dicts so a product list's own PII-shaped fields (a customer note, for
    instance) are dropped too, not just the top level.

    Stable identifiers are pseudonymised rather than passed through or
    dropped, so the fixture keeps its internal references without carrying
    real ids.

    `aliases`: defaults to a fresh map, same as before --
    but a caller sanitizing several responses that belong to ONE bundle
    (a cart read, its own write response, a catalogue lookup) must pass
    the SAME dict across every call, mutated in place. Without this, the
    same real cart id gets a different alias in each response --
    referential integrity held within one payload and broke across a
    multi-call bundle, and `authorize_write` then refuses on "cart id
    changed since consent was granted" for a reason that looks like a
    graph bug, not a sanitization one.
    """
    if aliases is None:
        aliases = {}
    return _sanitize_dict(raw, aliases=aliases)


def _sanitize_dict(raw: Dict[str, Any], aliases: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        if key == "context" and isinstance(value, dict):
            out[key] = {
                k: (_pseudonymise(k, v, aliases) if k in _PSEUDONYMISED_KEYS else v)
                for k, v in value.items()
                if k in _ALLOWED_CONTEXT_KEYS
            }
            continue
        if key not in ALLOWED_KEYS:
            continue
        if key in _PSEUDONYMISED_KEYS and isinstance(value, str):
            out[key] = _pseudonymise(key, value, aliases)
            continue
        out[key] = _sanitize_value(value, aliases)
    return out


_UUID_SHAPE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _pseudonymise(key: str, value: Any, aliases: Dict[str, str]) -> Any:
    """Same original id -> same replacement, within one sanitize run.

    a UUID-shaped original gets a UUID-shaped pseudonym. The readable
    `test_id_001` form is not UUID-shaped, and
    `domain/evidence_gate.gate_candidates` requires `product_uuid`,
    `company_id` and `branch_id` to BE UUID-shaped (an earlier decision the three
    arguments the write tool's own inputSchema demands). A sanitized
    bundle therefore had every candidate rejected by the Evidence Gate on
    replay, reaching `no_action_available` with no receipts: a bundle
    unable to pass its own gate. The replacement is still obviously
    synthetic (an all-zero prefix and a counter) and still deterministic,
    so no real id is published and referential integrity holds.
    """
    if not isinstance(value, str):
        return value
    if value not in aliases:
        index = len(aliases) + 1
        if _UUID_SHAPE.match(value):
            aliases[value] = f"00000000-0000-4000-8000-{index:012d}"
        else:
            aliases[value] = f"{_PSEUDONYMISED_KEYS[key]}_{index:03d}"
    return aliases[value]


def _sanitize_value(value: Any, aliases: Dict[str, str]) -> Any:
    if isinstance(value, dict):
        return _sanitize_dict(value, aliases)
    if isinstance(value, list):
        return [_sanitize_value(item, aliases) for item in value]
    return value
