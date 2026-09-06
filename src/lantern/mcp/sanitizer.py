"""F7: allow-list based fixture sanitization —
anything not explicitly reviewed is dropped, never passed through by
default. `scripts/sanitize_fixture.py` (G2) is the thin CLI wrapper that
reads a raw captured payload, calls `sanitize_payload`, and writes the
result into `datasets/fixtures/sanitized/`.

The field list below is a first cut from the G0 evidence lab's own
documented cart-snapshot fields (`notebooks/evidence_lab.ipynb`) for
non-PII, product/pricing-level data. It is not a claim of completeness for
every field the live server can return — every sanitized fixture still needs
a human review pass before commit (F7's own review checklist: does an
allowed field's *value* look like free text that could carry PII).
"""

from typing import Any, Dict

# Product/pricing-level fields only — no address, contact, or free-text
# fields. Extend this list only after reviewing what a real capture
# actually contains, never by guessing what "seems safe".
#
# Widened 2026-09-06 against the real `silpo_get_shopping_cart_by_id` wire
# shape (G3's own live captures) — the original list was built from the
# evidence notebook's own *flattened* view (`productsTotal`, `deliveryType`
# at the top level) and did not include the structural nesting keys
# (`cart`, `calculation`, `shipments`) the raw wire response actually uses,
# so sanitizing a real capture silently produced an empty payload. `address`
# is deliberately never added — it carries exact coordinates and a street
# address, which plan section 12.1.1 step 3 requires removed, not allowed.
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
    }
)


# Keys whose *values* are stable identifiers tying a fixture back to a real
# account, branch or catalogue entry. Plan section 12.1.1 step 3 requires
# these replaced with local `test_*` values "зі збереженням посилальної
# цілісності" — dropping them would break the references between a
# validation's `productId` and the line item it points at, and passing them
# through would publish real ids. They are pseudonymised instead, with one
# stable mapping per sanitize run so every reference to the same original
# id lands on the same replacement.
_PSEUDONYMISED_KEYS = {
    "productId": "test_product",
    "companyId": "test_company",
    "branchId": "test_branch",
    "cartId": "test_cart",
    "shoppingCartId": "test_cart",
}

# `context` is a free-form object the server fills as it likes, so it is not
# allow-listed wholesale. These are the keys measured in real captures, and
# `orderCostMin` in particular is load-bearing: without it a fixture cannot
# exercise DR-03's gap at all.
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


def sanitize_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Keeps only allow-listed keys, recursing into nested dicts and lists
    of dicts so a product list's own PII-shaped fields (a customer note, for
    instance) are dropped too, not just the top level.

    Stable identifiers are pseudonymised rather than passed through or
    dropped, so the fixture keeps its internal references without carrying
    real ids (plan section 12.1.1 step 3).
    """
    return _sanitize_dict(raw, aliases={})


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


def _pseudonymise(key: str, value: Any, aliases: Dict[str, str]) -> Any:
    """Same original id -> same replacement, within one sanitize run."""
    if not isinstance(value, str):
        return value
    if value not in aliases:
        aliases[value] = f"{_PSEUDONYMISED_KEYS[key]}_{len(aliases) + 1:03d}"
    return aliases[value]


def _sanitize_value(value: Any, aliases: Dict[str, str]) -> Any:
    if isinstance(value, dict):
        return _sanitize_dict(value, aliases)
    if isinstance(value, list):
        return [_sanitize_value(item, aliases) for item in value]
    return value
