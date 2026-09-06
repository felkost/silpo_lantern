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
ALLOWED_KEYS = frozenset(
    {
        "productId",
        "companyId",
        "name",
        "slug",
        "price",
        "subDiscount",
        "quantity",
        "stock",
        "productsTotal",
        "total",
        "totalAfterDiscounts",
        "deliveryType",
        "minOrderCost",
        "deliveryCost",
        "products",
        "validations",
        "level",
        "message",
        "code",
    }
)


def sanitize_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Keeps only allow-listed keys, recursing into nested dicts and lists
    of dicts so a product list's own PII-shaped fields (a customer note, for
    instance) are dropped too, not just the top level.
    """
    return {
        key: _sanitize_value(value) for key, value in raw.items() if key in ALLOWED_KEYS
    }


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return sanitize_payload(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value
