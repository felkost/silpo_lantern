"""F7: allow-list at the key level — anything not
explicitly reviewed is dropped, never passed through by default (safer than
a deny-list, which only protects against PII shapes someone already thought
of). The concrete field list here is a first cut built from the G0 evidence
lab's own documented cart-snapshot fields (notebooks/evidence_lab.ipynb) for
the non-PII, product-level data; it is a **required human review** step
before any real captured payload is sanitized and committed — not a claim
that this list is complete for every field the live server can return.
"""

from src.lantern.mcp.sanitizer import sanitize_payload


def test_keeps_only_allowlisted_keys() -> None:
    raw = {"productId": "p1", "name": "Молоко", "price": 39.99, "unexpected_field": "x"}
    sanitized = sanitize_payload(raw)
    assert sanitized == {"productId": "p1", "name": "Молоко", "price": 39.99}


def test_drops_address_and_contact_shaped_fields() -> None:
    raw = {
        "productId": "p1",
        "price": 10,
        "address": {"street": "Хрещатик", "houseNumber": "1"},
        "phone": "+380000000000",
        "email": "guest@example.com",
    }
    sanitized = sanitize_payload(raw)
    assert "address" not in sanitized
    assert "phone" not in sanitized
    assert "email" not in sanitized


def test_recurses_into_nested_lists_of_dicts() -> None:
    raw = {
        "products": [
            {"productId": "p1", "price": 10, "customerNote": "leave at door"},
            {"productId": "p2", "price": 20},
        ]
    }
    sanitized = sanitize_payload(raw)
    assert sanitized["products"] == [
        {"productId": "p1", "price": 10},
        {"productId": "p2", "price": 20},
    ]


def test_an_empty_payload_stays_empty() -> None:
    assert sanitize_payload({}) == {}
