"""T16 (G8 stage spec): the compensation offer reaches the guest through
`GET /session/{id}/events`. Two things the ordinary add path never
exercised: the offer is emitted from `persist_receipt`'s own chunk (not
`explain`, which is not on the compensation path at all), and it carries
`kind`/`compensates_action_id` so the client knows to render the undo
copy. A repeated GET at the offer must replay the receipt ABOVE it too --
this also fixes the same latent hole for D42's own second round, which
never had a declared test for it either.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api import routes as routes_module
from apps.api.limits import SpendCaps
from apps.api.session_cookie import SESSION_COOKIE
from src.lantern.domain.models import ActionProposal, Cart, EvidenceTuple, Receipt

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def _add_proposal() -> ActionProposal:
    return ActionProposal(
        action_id="a1",
        tool_name="silpo_add_or_update_cart_products",
        product_name="Товар",
        quantity=Decimal("1"),
        expected_delta=Decimal("86.84"),
        canonical_args={
            "shoppingCartId": "cart-1",
            "products": [
                {
                    "productId": "p1",
                    "companyId": "c1",
                    "branchId": "b1",
                    "quantity": 1,
                    "addQuantity": False,
                }
            ],
        },
        evidence=[
            EvidenceTuple(
                product_id="p1",
                price=Decimal("86.84"),
                availability=True,
                source_tool="silpo_find_products_batch",
                captured_at=_NOW,
            )
        ],
        guest_text_uk="Додати товар",
    )


def _compensation_proposal() -> ActionProposal:
    return ActionProposal(
        action_id="comp-1",
        tool_name="silpo_remove_cart_products",
        product_name="Товар",
        quantity=Decimal("-1"),
        expected_delta=Decimal("-86.84"),
        canonical_args={"shoppingCartId": "cart-1", "products": [{"productId": "p1"}]},
        evidence=[
            EvidenceTuple(
                product_id="p1",
                price=Decimal("86.84"),
                availability=True,
                source_tool="silpo_get_shopping_cart_by_id",
                captured_at=_NOW,
            )
        ],
        guest_text_uk="Повернути товар",
        kind="compensate",
        compensates_action_id="a1",
    )


def _receipt() -> Receipt:
    return Receipt(
        action_id="a1",
        session_id="s1",
        owner="owner-hash-1",
        before_state={"cart_id": "cart-1", "products_total": "500.77", "products": []},
        after_state={
            "cart_id": "cart-1",
            "products_total": "587.61",
            "products": [
                {"product_id": "p1", "name": "Товар", "quantity": "1", "price": "86.84"}
            ],
        },
        verified=True,
        status="receipt",
        reason="",
        expected_delta=Decimal("86.84"),
        actual_delta=Decimal("86.84"),
        created_at=_NOW,
        blocker_cleared=False,
        kind="add",
    )


class _FakeTokenStorage:
    async def get_tokens(self) -> object:
        return "a-token"


class _FakeStateSnapshot:
    def __init__(self, values: Dict[str, Any]) -> None:
        self.values = values


class _FakeGraph:
    def __init__(self, chunks, final_state, initial_state=None) -> None:
        self.chunks = chunks
        self.final_state = final_state
        self.state = initial_state if initial_state is not None else {}
        self.astream_inputs = []

    async def astream(self, input_, config, stream_mode="updates"):
        self.astream_inputs.append(input_)
        for chunk in self.chunks:
            yield chunk
        self.state = self.final_state

    async def aget_state(self, config):
        return _FakeStateSnapshot(self.state)

    async def aupdate_state(self, config, values):
        self.state = {**self.state, **values}


def _client(app: FastAPI) -> TestClient:
    """G10 (A-G10-04): every `/session/{id}/*` route checks the path id
    against the session cookie; each test here drives session `s1`."""
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, "s1")
    return client


def _make_app(graph: _FakeGraph, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_module.router)
    app.state.graph_builder = lambda: graph
    app.state.owner_secret = "test-owner-secret"
    app.state.repo_pool = object()
    app.state.version_tuple = {"schema_hash": "h1"}
    app.state.spend_caps = SpendCaps()

    monkeypatch.setattr(routes_module.repository, "create_session", lambda *a: None)
    monkeypatch.setattr(
        routes_module, "SessionTokenStorage", lambda pool, sid: _FakeTokenStorage()
    )
    monkeypatch.setattr(routes_module.repository, "save_consent", lambda *a: None)
    monkeypatch.setattr(
        routes_module.repository,
        "get_session",
        lambda *a: {"session_id": "s1", "thread_id": "s1", "owner": "owner-hash-1"},
    )
    return app


def test_the_offer_is_emitted_from_persist_receipt_not_only_explain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The compensation offer's chunk comes from `persist_receipt`, which
    the endpoint used to ignore entirely for `options` -- only `explain`'s
    chunk was checked."""
    final_state = {
        "session_id": "s1",
        "trace_id": "t1",
        "owner": "owner-hash-1",
        "status": "awaiting_consent",
        "error": None,
        "cart": Cart(cart_id="cart-1", products_total=Decimal("587.61")),
        "diagnosis": None,
        "disclosure": None,
        "channel_comparison": [],
        "candidates": [_compensation_proposal()],
        "consent_action_id": None,
        "consent": None,
        "receipt": _receipt(),
        "write_response": None,
    }
    graph = _FakeGraph(
        chunks=[
            {"persist_receipt": {"receipt": _receipt(), "status": "aborted"}},
            {
                "persist_receipt": {
                    "candidates": [_compensation_proposal()],
                    "status": "awaiting_consent",
                }
            },
            {"__interrupt__": ()},
        ],
        final_state=final_state,
        initial_state={
            "status": "awaiting_consent",
            "consent_action_id": "a1",
            "candidates": [_add_proposal()],
        },
    )
    app = _make_app(graph, monkeypatch)
    client = _client(app)

    response = client.get("/session/s1/events")

    assert "event: options" in response.text
    assert '"kind": "compensate"' in response.text
    assert '"compensates_action_id": "a1"' in response.text


def test_a_repeated_get_at_the_offer_replays_the_receipt_above_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "session_id": "s1",
        "trace_id": "t1",
        "owner": "owner-hash-1",
        "status": "awaiting_consent",
        "error": None,
        "cart": Cart(cart_id="cart-1", products_total=Decimal("587.61")),
        "diagnosis": None,
        "disclosure": None,
        "channel_comparison": [],
        "candidates": [_compensation_proposal()],
        "consent_action_id": None,
        "consent": None,
        "receipt": _receipt(),
        "write_response": None,
    }
    graph = _FakeGraph(chunks=[], final_state=state, initial_state=state)
    app = _make_app(graph, monkeypatch)
    client = _client(app)

    response = client.get("/session/s1/events")

    assert graph.astream_inputs == []  # never advanced
    assert "event: receipt" in response.text
    assert "event: options" in response.text
    assert '"kind": "compensate"' in response.text
