"""two forced changes to the sanitizer, found by
an adversarial audit of this stage's plan against `sanitize_payload`'s
actual coverage.

[A-5]: `ALLOWED_KEYS` was built for cart-snapshot fields; sanitizing a
`find_products_batch`/`time_slots`/`delivery_types`/write response with
the earlier list silently produced `{}` -- the same failure mode
`sanitize_fixture.py`'s own 2026-09-06 note already records for the cart
shape. Verified below with the ACTUAL response shapes
`tests/unit/test_write_path_interrupt_and_resume.py` uses.

[A-6]: `sanitize_payload` started a fresh alias map on every call, so
sanitizing the several responses that belong to one bundle independently
gave the same real id a DIFFERENT alias in each response -- referential
integrity held within one payload and broke across a multi-call bundle.
"""

from typing import Any, Dict

from src.lantern.mcp.sanitizer import sanitize_payload

_FIND_PRODUCTS_RESPONSE: Dict[str, Any] = {
    "queries": [
        {
            "query": "Молоко «Галичина» 2,5%",
            "products": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "Молоко «Галичина» 2,5%",
                    "slug": "moloko-halychyna",
                    "price": 39.99,
                    "stock": 600,
                    "weighted": False,
                    "step": 1,
                    "available": True,
                    "companyId": "22222222-2222-2222-2222-222222222222",
                    "branchId": "33333333-3333-3333-3333-333333333333",
                    "externalProductId": 795319,
                }
            ],
        }
    ]
}

_TIME_SLOTS_RESPONSE: Dict[str, Any] = {
    "slots": [
        {
            "start": "2026-09-08T10:00:00Z",
            "end": "2026-09-08T12:00:00Z",
            "available": True,
            "deliveryType": "SelfPickup",
            "deliveryCost": 0,
            "deliveryCostMap": [],
            "minOrderCost": 199,
        }
    ]
}

_DELIVERY_TYPES_RESPONSE: Dict[str, Any] = {
    "success": True,
    "summary": "",
    "options": [{"deliveryType": "SelfPickup", "branchId": "b1"}],
}

_WRITE_RESPONSE: Dict[str, Any] = {
    "success": True,
    "summary": "ok",
    "products": [{"productId": "p1", "quantity": 1}],
}


def test_find_products_batch_response_does_not_sanitize_to_empty() -> None:
    sanitized = sanitize_payload(_FIND_PRODUCTS_RESPONSE)
    assert sanitized != {}
    product = sanitized["queries"][0]["products"][0]
    assert product["name"] == "Молоко «Галичина» 2,5%"
    assert product["price"] == 39.99
    assert product["step"] == 1
    assert product["available"] is True
    assert product["externalProductId"] == 795319
    # A bare identifier: pseudonymised, not passed through raw.
    assert product["id"] != "11111111-1111-1111-1111-111111111111"
    # a UUID-shaped original keeps a UUID-shaped pseudonym -- the
    # Evidence Gate requires that shape, and the old
    # `test_id_NNN` form made every candidate in a sanitized bundle fail
    # the gate on replay. Still obviously synthetic, still deterministic.
    assert product["id"].startswith("00000000-0000-4000-8000-")


def test_time_slots_response_does_not_sanitize_to_empty() -> None:
    sanitized = sanitize_payload(_TIME_SLOTS_RESPONSE)
    assert sanitized != {}
    slot = sanitized["slots"][0]
    assert slot["deliveryType"] == "SelfPickup"
    assert slot["minOrderCost"] == 199
    assert slot["deliveryCostMap"] == []


def test_delivery_types_response_does_not_sanitize_to_empty() -> None:
    sanitized = sanitize_payload(_DELIVERY_TYPES_RESPONSE)
    assert sanitized != {}
    assert sanitized["options"][0]["deliveryType"] == "SelfPickup"


def test_write_response_does_not_sanitize_to_empty() -> None:
    sanitized = sanitize_payload(_WRITE_RESPONSE)
    assert sanitized != {}
    assert sanitized["summary"] == "ok"
    assert sanitized["success"] is True


def test_a_shared_alias_map_keeps_the_same_cart_id_stable_across_responses() -> None:
    """The exact regression [A-6] found. `cart_response` pseudonymises
    TWO other identifiers before it reaches `shoppingCartId`, so on a
    FRESH map that id becomes the map's third entry; `write_response`
    sanitized independently sees `shoppingCartId` FIRST, so on its own
    fresh map it becomes the first entry -- same real cart id, two
    different aliases. A bundle player would then see two different
    `shoppingCartId` values for one cart, and `authorize_write` refuses
    on 'cart id changed since consent was granted' for a reason that has
    nothing to do with the graph."""
    cart_response = {
        "companyId": "real-company-uuid",
        "branchId": "real-branch-uuid",
        "shoppingCartId": "real-cart-uuid",
    }
    write_response = {"shoppingCartId": "real-cart-uuid", "success": True}

    # Reproduces the bug: two independent (fresh-map) calls.
    fresh_cart = sanitize_payload(cart_response)
    fresh_write = sanitize_payload(write_response)
    assert fresh_cart["shoppingCartId"] != fresh_write["shoppingCartId"], (
        "demonstrates the bug this fix closes -- without a shared map, "
        "the same real cart id sanitizes to two different aliases "
        "depending on what else was pseudonymised first in each call"
    )

    # The fix: one shared map across every response in the bundle.
    shared_aliases: Dict[str, str] = {}
    got_cart = sanitize_payload(cart_response, aliases=shared_aliases)
    got_write = sanitize_payload(write_response, aliases=shared_aliases)
    assert got_cart["shoppingCartId"] == got_write["shoppingCartId"]
