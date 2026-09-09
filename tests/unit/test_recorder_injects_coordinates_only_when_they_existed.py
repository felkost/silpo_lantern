"""G9 (1.4): `_build_draft_from_tape` restores synthetic coordinates onto
a taped cart, because the sanitizer strips the guest's real address and
`compare_channels_node` needs SOME coordinates or it degrades to a no-op
(D-G7-07). That is right for a LIVE capture, whose cart genuinely had an
address before sanitization.

It is wrong for an offline synthesis from a coordinate-less synthetic
cart: injecting coordinates makes `compare_channels_node` RUN during
replay and call `silpo_get_available_delivery_types` -- a call the tape
cannot serve, because the taped run (against the same coordinate-less
cart) never made it. The bundle then fails its own self-consistency
replay with a `ReplayMismatch`.

Found while synthesizing GD-03's bundle offline. Injection is now
conditional on the cart having carried coordinates in the first place.
"""

from scripts.record_replay_bundle import _build_draft_from_tape

_CART_WITH_ADDRESS = {
    "cart": {
        "id": "cart-1",
        "address": {"latitude": 49.1, "longitude": 28.2},
        "calculation": {"productsTotal": 100.0, "validations": []},
        "shipments": [],
    }
}

_CART_WITHOUT_ADDRESS = {
    "cart": {
        "id": "cart-1",
        "calculation": {"productsTotal": 100.0, "validations": []},
        "shipments": [],
    }
}


def _tape_with(cart_response: dict) -> dict:
    return {
        "mcp": [
            ("silpo_get_shopping_cart_by_id", {"cart_id": "cart-1"}, cart_response)
        ],
        "planner": [],
        "explainer": [],
    }


def _cart_in(draft: dict) -> dict:
    queue = next(iter(draft["payload"]["mcp"].values()))
    return dict(queue[0]["cart"])


def test_a_cart_that_had_coordinates_gets_synthetic_ones_back() -> None:
    """A live capture's real address is stripped by the sanitizer;
    synthetic coordinates restore what compare_channels needs."""
    draft = _build_draft_from_tape(_tape_with(_CART_WITH_ADDRESS))
    cart = _cart_in(draft)

    assert "address" in cart
    assert cart["address"]["latitude"] is not None
    assert cart["address"]["latitude"] != 49.1, "the REAL coordinate must not survive"


def test_a_cart_that_never_had_coordinates_does_not_gain_them() -> None:
    """An offline synthetic cart never had an address. Injecting one makes
    compare_channels call a tool the tape never recorded, and the bundle
    fails its own replay."""
    draft = _build_draft_from_tape(_tape_with(_CART_WITHOUT_ADDRESS))
    cart = _cart_in(draft)

    assert "address" not in cart, (
        "coordinates were injected into a cart that never had any -- replay "
        "will now call silpo_get_available_delivery_types, which the tape "
        "cannot serve"
    )
