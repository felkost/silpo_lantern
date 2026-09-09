"""G9 (D73): the key a bundle stores for a taped call must equal the key
`replay()` computes for that same call.

`_build_draft_from_tape` ran the taped ARGS through `sanitize_payload`,
which is the RESPONSE allow-list: it keeps wire names (`shoppingCartId`,
`branchId`) and drops everything else. The taped args use the INTERNAL
snake_case names `graph/replay.py`'s own fetcher closures build
(`cart_id`, `branch_id`, `latitude`, ...), none of which are on that
list -- so almost every args dict sanitized to `{}`, and four different
tools' calls all keyed to `sha256("{}")`. `replay()` meanwhile computes
its key from the REAL internal args, so the args-keyed lookup could never
match: every call fell through to the ordered `mcp_by_tool` fallback, and
ordering alone decided what got served.

That is why a live-recorded bundle replayed to `unverified` with one
receipt against the live run's `verified` with four -- a later
`find_products_batch` response was served for round one, so the graph
consented to one product and the read-back showed another.

The identifiers in the args still must not be real, and must match the
pseudonyms used in the RESPONSES, or the guard refuses on "cart id changed
since consent was granted". So args are pseudonymised through the same
shared alias map -- values only, keys preserved.
"""

from src.lantern.graph.replay import response_key
from scripts.record_replay_bundle import (
    SYNTHETIC_LATITUDE,
    SYNTHETIC_LONGITUDE,
    _build_draft_from_tape,
)

_REAL_CART_ID = "4e83e418-a6b1-4187-b961-f8c9fb4ba2f5"
_REAL_BRANCH_ID = "1edb735c-78eb-6d24-9dc9-d5cf071d641d"


def _tape() -> dict:
    cart_response = {
        "cart": {
            "id": _REAL_CART_ID,
            "address": {"latitude": 50.74, "longitude": 25.32},
            "calculation": {"productsTotal": 100.0, "validations": []},
            "shipments": [{"branchId": _REAL_BRANCH_ID, "products": []}],
        }
    }
    return {
        "mcp": [
            ("silpo_get_my_shopping_cart", {}, {"shoppingCartId": _REAL_CART_ID}),
            (
                "silpo_get_shopping_cart_by_id",
                {"cart_id": _REAL_CART_ID},
                cart_response,
            ),
            (
                "silpo_get_available_delivery_types",
                {"latitude": 50.74, "longitude": 25.32},
                {"options": []},
            ),
            (
                "silpo_get_time_slots",
                {"branch_id": _REAL_BRANCH_ID, "delivery_types": ["DeliveryHome"]},
                {"slots": []},
            ),
        ],
        "planner": [],
        "explainer": [],
    }


def _keys(draft: dict):
    return set(draft["payload"]["mcp"].keys())


def test_each_tool_gets_its_own_key_not_one_shared_empty_one() -> None:
    keys = _keys(_build_draft_from_tape(_tape()))

    tools = {key.split(":")[0] for key in keys}
    assert len(tools) == 4, f"expected four distinct tools, got {tools}"
    # The bug: four tools, four keys, all with the SAME digest because
    # every args dict had sanitized to `{}`.
    digests = {key.split(":")[1] for key in keys}
    assert (
        len(digests) == 4
    ), f"tools share a digest -- args were flattened to a constant: {keys}"


def test_the_argument_keys_survive_sanitisation() -> None:
    """`cart_id` must still be `cart_id` in the key's own input -- the
    response allow-list would have dropped it."""
    draft = _build_draft_from_tape(_tape())
    pseudonymised_cart_id = draft["payload"]["mcp"][
        next(k for k in _keys(draft) if k.startswith("silpo_get_shopping_cart_by_id"))
    ][0]["cart"]["id"]

    expected = response_key(
        "silpo_get_shopping_cart_by_id", {"cart_id": pseudonymised_cart_id}
    )

    assert expected in _keys(
        draft
    ), "the key replay() will compute for this call is not in the bundle"


def test_a_real_identifier_never_reaches_the_key_input() -> None:
    draft = _build_draft_from_tape(_tape())
    real_key = response_key("silpo_get_shopping_cart_by_id", {"cart_id": _REAL_CART_ID})
    assert real_key not in _keys(draft), "the REAL cart id was keyed on"


def test_coordinates_in_args_are_the_synthetic_pair() -> None:
    """`compare_channels` passes the cart's own coordinates, and the
    replayed cart carries the SYNTHETIC pair -- so the key recorded for
    that call must be built from the synthetic pair too, or it can never
    match."""
    draft = _build_draft_from_tape(_tape())
    expected = response_key(
        "silpo_get_available_delivery_types",
        {"latitude": SYNTHETIC_LATITUDE, "longitude": SYNTHETIC_LONGITUDE},
    )
    assert expected in _keys(draft)
