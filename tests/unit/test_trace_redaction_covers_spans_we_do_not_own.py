"""The coordinates must not reach LangSmith from ANY span, including the
ones this project never created.

`redact_planner_input` drops them from its own span and says why: address-
adjacent data has no legitimate reason to reach a third-party trace. That
held for the three calls `tracer.py` wraps and for nothing else — LangGraph
instruments every node itself and serialises the whole `RecoveryState`. A
trace exported from a real run on 2026-09-07 carried `latitude: 50.745204`
and `longitude: 25.321071` verbatim in a neighbouring span, alongside the
cart id, every product id, the consent record and two full cart snapshots
inside the receipt.

`strip_coordinates` is installed on LangSmith's process-wide client, which
is the one lever that reaches spans nobody here wrote.
"""

from typing import Any, Dict

import pytest

from src.lantern.observability.tracer import (
    COORDINATE_KEYS,
    install_trace_redaction,
    strip_coordinates,
)

_REAL_STATE: Dict[str, Any] = {
    "session_id": "s1",
    "cart": {
        "cart_id": "4e83e418-a6b1-4187-b961-f8c9fb4ba2f5",
        "latitude": 50.745204,
        "longitude": 25.321071,
        "products": [{"product_id": "p1", "name": "Молоко", "price": "39.99"}],
    },
    "receipt": {
        "before_state": {"latitude": 50.745204, "longitude": 25.321071},
        "after_state": {"latitude": 50.745204, "longitude": 25.321071},
    },
    "channel_snapshots": [{"latitude": 50.745204, "longitude": 25.321071}],
}


def test_coordinates_are_removed_at_every_depth() -> None:
    """The real payload nests them four ways: on the cart, inside both cart
    snapshots the receipt carries, and inside a list of channel
    snapshots."""
    redacted = strip_coordinates(_REAL_STATE)

    rendered = repr(redacted)
    assert "50.745204" not in rendered
    assert "25.321071" not in rendered


def test_everything_else_survives() -> None:
    """A redactor that strips too much makes the trace useless, which is
    how it ends up switched off."""
    redacted = strip_coordinates(_REAL_STATE)

    assert redacted["session_id"] == "s1"
    assert redacted["cart"]["cart_id"] == "4e83e418-a6b1-4187-b961-f8c9fb4ba2f5"
    assert redacted["cart"]["products"][0]["name"] == "Молоко"
    assert set(redacted["cart"]) == {"cart_id", "products"}


def test_a_payload_with_no_coordinates_is_unchanged() -> None:
    payload = {"a": [1, 2, {"b": "c"}], "d": None}

    assert strip_coordinates(payload) == payload


def test_the_hook_is_actually_installed_or_it_raises() -> None:
    """A redactor that silently failed to install is worse than none: the
    trace looks supervised while nothing is being stripped. `install` is
    idempotent when it is the one that primed the client, and raises when
    something else got there first.
    """
    install_trace_redaction()

    from langsmith.run_trees import get_cached_client

    assert get_cached_client()._hide_inputs is strip_coordinates
    assert get_cached_client()._hide_outputs is strip_coordinates

    # Calling it again must not raise: the cached client is already ours.
    install_trace_redaction()


def test_it_raises_when_a_foreign_client_got_there_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Foreign:
        _hide_inputs = None

    monkeypatch.setattr(
        "src.lantern.observability.tracer.get_cached_client",
        lambda **kwargs: _Foreign(),
    )

    with pytest.raises(RuntimeError, match="already existed"):
        install_trace_redaction()


def test_the_coordinate_key_set_is_not_silently_empty() -> None:
    assert COORDINATE_KEYS == frozenset({"latitude", "longitude"})
