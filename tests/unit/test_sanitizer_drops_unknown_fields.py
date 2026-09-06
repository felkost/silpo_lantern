"""Allow-list at the key level — anything not
explicitly reviewed is dropped, never passed through by default (safer than
a deny-list, which only protects against PII shapes someone already thought
of). The concrete field list here is a first cut built from documented
cart-snapshot fields (notebooks/evidence_lab.ipynb) for
the non-PII, product-level data; it is a **required human review** step
before any real captured payload is sanitized and committed — not a claim
that this list is complete for every field the live server can return.
"""

from src.lantern.mcp.sanitizer import sanitize_payload


def test_keeps_only_allowlisted_keys() -> None:
    raw = {"productId": "p1", "name": "Молоко", "price": 39.99, "unexpected_field": "x"}
    sanitized = sanitize_payload(raw)
    # `productId` survives but pseudonymised — stable identifiers are
    # replaced, not passed through.
    assert sanitized == {
        "productId": "test_product_001",
        "name": "Молоко",
        "price": 39.99,
    }


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
        {"productId": "test_product_001", "price": 10},
        {"productId": "test_product_002", "price": 20},
    ]


def test_an_empty_payload_stays_empty() -> None:
    assert sanitize_payload({}) == {}


def test_identifiers_are_pseudonymised_with_referential_integrity() -> None:
    """Stable identifiers are replaced with
    local `test_*` values "зі збереженням посилальної цілісності" — the
    same original id must land on the same replacement everywhere in one
    payload, or a validation's `productId` stops pointing at its line item.
    """
    raw = {
        "shipments": [
            {
                "companyId": "real-company-uuid",
                "products": [
                    {"productId": "real-product-uuid", "price": 10},
                    {"productId": "other-product-uuid", "price": 20},
                ],
            }
        ],
        "validations": [
            {
                "level": "error",
                "type": "product",
                "message": "product.offer.not_found",
                "context": {"productId": "real-product-uuid"},
            }
        ],
    }
    sanitized = sanitize_payload(raw)

    first_item = sanitized["shipments"][0]["products"][0]["productId"]
    second_item = sanitized["shipments"][0]["products"][1]["productId"]
    referenced = sanitized["validations"][0]["context"]["productId"]

    assert not first_item.startswith("real-")
    assert first_item != second_item
    # the reference still resolves to the same (pseudonymised) product
    assert referenced == first_item


def test_validation_context_keeps_the_load_bearing_threshold() -> None:
    """`context` is not allow-listed wholesale, but `orderCostMin` is the
    field the whole gap calculation depends on — a fixture that drops it
    cannot exercise the hero rule at all."""
    raw = {
        "validations": [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 599, "unreviewed_field": "dropped"},
            }
        ]
    }
    sanitized = sanitize_payload(raw)
    context = sanitized["validations"][0]["context"]
    assert context == {"orderCostMin": 599}
