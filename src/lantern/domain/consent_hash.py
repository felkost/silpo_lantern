"""`args_hash`/`state_hash` construction. Defined here, not left as
a bare `str` field on `ConsentRecord`, because the consent-binding
invariant ("re-read стан = consent стан, інакше STOP")
depends entirely on this value being reproducible — a field with no defined
algorithm would let any schema-only test pass regardless of what a later
stage invents.
"""

import hashlib
import json
from decimal import Decimal
from typing import Any, Mapping

from src.lantern.domain.models import Cart


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Stable JSON for hashing: sorted keys and no whitespace, so two
    structurally-equal payloads with different key insertion order hash
    identically.
    `Decimal` values serialize via their exact string form, never through
    `float`'s binary approximation; any other non-JSON-safe type raises
    rather than being silently coerced."""

    def default(value: object) -> str:
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(f"not canonicalizable for hashing: {type(value).__name__}")

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=default,
    )


def compute_args_hash(canonical_args: Mapping[str, Any]) -> str:
    """sha256 over `canonical_json(canonical_args)` — the write's own
    arguments, bound to the consent record they were approved under."""
    return hashlib.sha256(canonical_json(canonical_args).encode("utf-8")).hexdigest()


def compute_state_hash(cart: Cart) -> str:
    """sha256 over the fields a write can actually change: cart id, the
    products total, and the sorted (product_id, quantity, price) triples.
    Deliberately excludes anything a write cannot affect (address,
    timeslot, restrictions) so an unrelated field changing between re-read
    and write does not spuriously invalidate a still-valid consent."""
    line_items = sorted(
        (
            {
                "product_id": item.product_id,
                "quantity": str(item.quantity),
                "price": str(item.price),
            }
            for item in cart.products
        ),
        key=lambda d: d["product_id"],
    )
    payload = {
        "cart_id": cart.cart_id,
        "products_total": str(cart.products_total),
        "line_items": line_items,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
