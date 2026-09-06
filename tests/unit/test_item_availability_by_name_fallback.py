"""Found while wiring `compare_channels_node`: the only tracked live cart
capture (`tests/unit/fixtures/d12_cart_wire_shape.json`) has an EMPTY
`shipments[].products[]` array — this project has never actually measured
a live cart line item's shape with an article code, and `LineItem.product_id`
(the cart's own internal `productId`) has no confirmed relationship to
`find_products_batch`'s `externalProductId`. Forcing that mapping without a
live measurement would be an invented fact.

`build_item_availability_by_name` is the honest fallback: `find_products_
batch` explicitly documents free-text name search as supported (its own
description, measured from the tracked contract fixture), so this matches
the cart's own line-item names against the channel's response — an
approximate signal, not a guaranteed-exact one, pending the first live
multi-item cart capture.
"""

from datetime import datetime, timezone

from src.lantern.domain.channel_snapshot_builder import (
    build_item_availability_by_name,
)

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

_RESPONSE = {
    "queries": [
        {
            "query": "Молоко «Галичина» 2,5%",
            "products": [
                {
                    "name": "Молоко «Галичина» 2,5%",
                    "available": True,
                    "price": 39.99,
                    "externalProductId": 1,
                }
            ],
        },
        {
            "query": "Хліб «Житній»",
            "products": [
                {
                    "name": "Хліб «Житній»",
                    "available": False,
                    "price": 25.0,
                    "externalProductId": 2,
                }
            ],
        },
    ]
}


def test_matches_by_name_case_insensitively() -> None:
    result = build_item_availability_by_name(
        expected_names=["молоко «галичина» 2,5%"],
        find_products_batch_response=_RESPONSE,
        call_id="call-1",
        captured_at=_NOW,
    )
    assert result == [True]


def test_a_name_found_but_unavailable_is_false() -> None:
    result = build_item_availability_by_name(
        expected_names=["Хліб «Житній»"],
        find_products_batch_response=_RESPONSE,
        call_id="call-1",
        captured_at=_NOW,
    )
    assert result == [False]


def test_a_name_absent_from_the_response_is_false_not_skipped() -> None:
    result = build_item_availability_by_name(
        expected_names=["Зовсім інший товар"],
        find_products_batch_response=_RESPONSE,
        call_id="call-1",
        captured_at=_NOW,
    )
    assert result == [False]
