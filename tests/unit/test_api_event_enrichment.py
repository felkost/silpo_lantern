"""G10 delivery C: the console's evidence rides on the existing events,
additively -- every value stringified at the boundary (a `Decimal` or
`datetime` reaching `json.dumps` raises INSIDE the streaming generator,
after a write may have landed: the G7 precedent). And no personal data
on the wire, asserted over every frame rather than reviewed (D-G10-08).
"""

import json
import re
from typing import Any, Dict, List

import pytest

from src.lantern.domain.consent_hash import compute_args_hash
from tests.unit.test_api_emits_compensation_option import _receipt
from tests.unit.test_api_session_routes import (
    _awaiting_consent_state,
    _client,
    _consented_state,
    _FakeGraph,
    _make_app,
    _proposal,
    _read_pipeline_chunks,
)

FORBIDDEN_KEYS = {
    "address",
    "phone",
    "email",
    "first_name",
    "last_name",
    "firstName",
    "lastName",
    "cart_id",
    "shoppingCartId",
    "latitude",
    "longitude",
    "before_state",
    "after_state",
    "canonical_args",
}


def _frames(body: str, event: str) -> List[Dict[str, Any]]:
    return [
        json.loads(m)
        for m in re.findall(rf"event: {event}\ndata: (.*?)\n\n", body, re.S)
    ]


def _keys(value: Any) -> set:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_diagnosis_carries_the_arithmetic_inputs_and_is_known(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=_read_pipeline_chunks(), final_state=_awaiting_consent_state()
    )
    client = _client(_make_app(graph, monkeypatch))

    (frame,) = _frames(client.get("/session/s1/events").text, "diagnosis")

    # Claim 2: money is computed by code -- the panel shows the inputs.
    assert frame["products_total"] == "404.89"
    assert frame["threshold_source"] == "validation_context"
    # `is_known` per validation: the quarantined codes render as unknown.
    for v in frame["validations"]:
        assert v["is_known"] in (True, False)


def test_options_carry_the_hash_and_the_evidence_but_no_product_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=_read_pipeline_chunks(), final_state=_awaiting_consent_state()
    )
    client = _client(_make_app(graph, monkeypatch))

    (frame,) = _frames(client.get("/session/s1/events").text, "options")

    (candidate,) = frame["candidates"]
    # Claim 3: the hash the guard will compare, computed with the guard's
    # own canonicalizer at emit time -- there is no such field in state.
    assert candidate["args_hash"] == compute_args_hash(_proposal().canonical_args)
    assert candidate["tool_name"] == "silpo_add_or_update_cart_products"
    (evidence,) = candidate["evidence"]
    assert evidence == {
        "price": "39.99",
        "availability": True,
        "source_tool": "silpo_find_products_batch",
        "captured_at": "2026-09-07T12:00:00+00:00",
    }


def test_receipt_carries_expected_delta_verified_and_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=[{"write_and_readback": {"receipt": _receipt(), "status": "verified"}}],
        final_state={**_consented_state(), "status": "verified", "receipt": _receipt()},
        initial_state=_consented_state(),
    )
    client = _client(_make_app(graph, monkeypatch))

    (frame,) = _frames(client.get("/session/s1/events").text, "receipt")

    assert frame["expected_delta"] == "86.84"
    assert frame["verified"] is True
    assert frame["kind"] == "add"


def test_consent_ack_carries_the_binding_but_no_cart_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=[], final_state={}, initial_state=_awaiting_consent_state()
    )
    client = _client(_make_app(graph, monkeypatch))

    body = client.post("/session/s1/consent", json={"action_id": "a1"}).json()

    assert body["args_hash"] == compute_args_hash(_proposal().canonical_args)
    assert re.fullmatch(r"[0-9a-f]{64}", body["state_hash"])
    assert body["expires_at"].endswith("+00:00")
    assert not FORBIDDEN_KEYS & set(body)


def test_no_frame_carries_a_forbidden_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-G10-08 on the wire: walk every frame of a read run and a write
    run for the keys that could carry a guest's identity or location."""
    read = _FakeGraph(
        chunks=_read_pipeline_chunks(), final_state=_awaiting_consent_state()
    )
    write = _FakeGraph(
        chunks=[{"write_and_readback": {"receipt": _receipt(), "status": "verified"}}],
        final_state={**_consented_state(), "status": "verified", "receipt": _receipt()},
        initial_state=_consented_state(),
    )
    for graph in (read, write):
        body = _client(_make_app(graph, monkeypatch)).get("/session/s1/events").text
        for match in re.findall(r"data: (.*?)\n\n", body, re.S):
            assert not FORBIDDEN_KEYS & _keys(json.loads(match)), match


def test_diagnosis_carries_the_cart_lines_but_no_id_or_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The console's cart column: what the server sees, so a jury has the
    starting state in front of them. Product names, quantities, prices,
    the total and the slot -- never the cart id, address or coordinates
    (the forbidden-key walk above covers every frame)."""
    from decimal import Decimal

    from src.lantern.domain.models import Cart, LineItem

    cart = Cart(
        cart_id="cart-1",
        products_total=Decimal("404.89"),
        delivery_type="DeliveryHome",
        products=[
            LineItem(
                product_id="p1",
                name="Молоко",
                quantity=Decimal("2"),
                price=Decimal("39.99"),
            ),
        ],
    )
    chunks = _read_pipeline_chunks()
    chunks[0] = {"read": {"cart": cart}}
    graph = _FakeGraph(
        chunks=chunks, final_state={**_awaiting_consent_state(), "cart": cart}
    )
    client = _client(_make_app(graph, monkeypatch))

    (frame,) = _frames(client.get("/session/s1/events").text, "diagnosis")

    assert frame["cart"]["delivery_type"] == "DeliveryHome"
    assert frame["cart"]["lines"] == [
        {"name": "Молоко", "quantity": "2", "price": "39.99"}
    ]
    assert "cart_id" not in frame["cart"] and "product_id" not in json.dumps(frame)


def test_receipt_carries_the_read_back_cart_and_null_when_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cart column's second state: the cart as the read-back saw it,
    projected the same way as the first (names, quantities, prices, total)
    -- never the wholesale `after_state`, which carries coordinates. An
    unreachable read-back (`after_state == {}`) yields null, not a guess."""
    from tests.unit.test_api_emits_compensation_option import _receipt as _r

    receipt = _r()
    unreachable = receipt.model_copy(
        update={"after_state": {}, "verified": False, "status": "unverified"}
    )
    graph = _FakeGraph(
        chunks=[
            {"write_and_readback": {"receipt": receipt, "status": "verified"}},
            {"persist_receipt": {"receipt": unreachable, "status": "unverified"}},
        ],
        final_state={
            **_consented_state(),
            "status": "unverified",
            "receipt": unreachable,
        },
        initial_state=_consented_state(),
    )
    client = _client(_make_app(graph, monkeypatch))

    first, second = _frames(client.get("/session/s1/events").text, "receipt")

    assert first["cart"]["products_total"] == "587.61"
    assert first["cart"]["lines"] == [
        {"name": "Товар", "quantity": "1", "price": "86.84"}
    ]
    assert second["cart"] is None
