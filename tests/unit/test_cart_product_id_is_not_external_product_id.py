"""Settles a risk carried since kickoff as "unmeasured" — the only
tracked live cart capture available had an EMPTY
`shipments[].products[]`, so this project had never seen a real line
item's shape. A live multi-item capture (the author added
diverse products to their own real cart) settles it definitively:
`LineItem.product_id` is a UUID (Silpo's own internal cart-line
identifier), structurally incompatible with `find_products_batch`'s
`externalProductId`, which is typed `number | null` in its own
`outputSchema`. These are two different identifier spaces by construction
— not merely "not yet observed to match" — confirming
`build_item_availability_by_name` (`channel_snapshot_builder.py`) is the
correct, necessary design, not a stopgap fallback pending better data.
"""

import json

from src.lantern.config import PROJECT_ROOT

FIXTURE_PATH = (
    PROJECT_ROOT
    / "datasets"
    / "fixtures"
    / "sanitized"
    / "cart_multi_item_diverse.json"
)


def _load_products() -> list:
    envelope = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    shipments = envelope["payload"]["cart"]["shipments"]
    return [p for shipment in shipments for p in shipment["products"]]


def test_fixture_has_multiple_diverse_line_items() -> None:
    """The exact residual risk carried forward: a multi-item,
    multi-price-point cart, not just a single-line fixture. Sanitizer
    pseudonymizes productId to `test_product_NNN`, so the check is on
    structure (count, distinct prices), not on the pseudonymized id text
    itself."""
    products = _load_products()
    assert len(products) >= 10
    distinct_prices = {p["price"] for p in products}
    assert len(distinct_prices) >= 5


def test_find_products_batch_external_product_id_is_typed_numeric() -> None:
    """Half of the incompatibility claim, verifiable from tracked data:
    `find_products_batch`'s own `outputSchema` types `externalProductId`
    as `number | null` (measured, tracked contract fixture). The OTHER
    half — that the live `productId` on this session's real cart was
    UUID-shaped (`1ed0765c-17fd-69fc-8ff2-dd63763181f9`-style), never a
    bare number — cannot be re-verified from committed data (the
    sanitizer deliberately destroys the real id, replacing it with
    `test_product_NNN`, which proves nothing about the original shape).
    """
    contract_fixture = (
        PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-05.json"
    )
    envelope = json.loads(contract_fixture.read_text(encoding="utf-8"))
    tools = {t["name"]: t for t in envelope["payload"]["tools"]}
    external_id_schema = tools["silpo_find_products_batch"]["outputSchema"][
        "properties"
    ]["queries"]["items"]["properties"]["products"]["items"]["properties"][
        "externalProductId"
    ]

    assert {"type": "number"} in external_id_schema["anyOf"]
    assert {"type": "null"} in external_id_schema["anyOf"]
