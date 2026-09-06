"""B2/B3 (G5+G6 stage spec): the session/consent/events routes, tested
against a FAKE graph (never a real MCP/LLM call, never a real Neon
connection -- `repository.create_session`/`save_consent` are monkeypatched
to no-ops, since `apps.api.routes` calls them as bare module functions).

T18: `ConsentRequest` accepts only `action_id` -- a client-supplied hash
has no field to land in at all, so tampering has nothing to overwrite.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api import routes as routes_module
from src.lantern.domain.models import ActionProposal, Diagnosis, EvidenceTuple

_NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


def _proposal(action_id: str = "a1") -> ActionProposal:
    return ActionProposal(
        action_id=action_id,
        tool_name="silpo_add_or_update_cart_products",
        product_name="Milk",
        quantity=Decimal("1"),
        expected_delta=Decimal("39.99"),
        canonical_args={
            "shoppingCartId": "cart-1",
            "products": [
                {
                    "productId": "11111111-1111-1111-1111-111111111111",
                    "companyId": "22222222-2222-2222-2222-222222222222",
                    "branchId": "33333333-3333-3333-3333-333333333333",
                    "quantity": 1,
                    "addQuantity": False,
                }
            ],
        },
        evidence=[
            EvidenceTuple(
                product_id="11111111-1111-1111-1111-111111111111",
                price=Decimal("39.99"),
                availability=True,
                source_tool="silpo_find_products_batch",
                captured_at=_NOW,
            )
        ],
        guest_text_uk="Додати товар",
    )


class _FakeStateSnapshot:
    def __init__(self, values: Dict[str, Any]) -> None:
        self.values = values


class _FakeGraph:
    """Stands in for a compiled `CompiledStateGraph`: `ainvoke` returns a
    fixed state, `aget_state` replays it, `aupdate_state` records the call
    for inspection. `resume_state`, when set, is what a resumed
    `ainvoke(None, ...)` returns -- simulating the Write Guard's own
    decision (a refusal, or a successful write) as a distinct outcome
    from the pre-resume `awaiting_consent` state `aget_state` still sees.
    """

    def __init__(
        self, state: Dict[str, Any], resume_state: Dict[str, Any] | None = None
    ) -> None:
        self.state = state
        self.resume_state = resume_state
        self.updated_with: Any = None

    async def ainvoke(self, input_: Any, config: Any) -> Dict[str, Any]:
        if input_ is None and self.resume_state is not None:
            return self.resume_state
        return self.state

    async def aget_state(self, config: Any) -> _FakeStateSnapshot:
        return _FakeStateSnapshot(self.state)

    async def aupdate_state(self, config: Any, values: Any) -> None:
        self.updated_with = values
        self.state = {**self.state, **values}


def _awaiting_consent_state() -> Dict[str, Any]:
    from src.lantern.domain.models import Cart

    return {
        "session_id": "s1",
        "trace_id": "t1",
        "owner": "owner-hash-1",
        "status": "awaiting_consent",
        "error": None,
        "cart": Cart(cart_id="cart-1", products_total=Decimal("404.89")),
        "diagnosis": Diagnosis(
            blockers=[],
            disclosures=[],
            gap=Decimal("194.11"),
            gap_is_borderline=False,
            primary_code="order.cost.min",
            threshold_source="validation_context",
        ),
        "candidates": [_proposal()],
        "consent_action_id": None,
        "consent": None,
        "receipt": None,
        "write_response": None,
    }


def _make_app(graph: _FakeGraph, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_module.router)
    app.state.graph_builder = lambda: graph
    app.state.owner_secret = "test-owner-secret"
    app.state.repo_pool = object()
    app.state.version_tuple = {"schema_hash": "h1"}

    monkeypatch.setattr(routes_module.repository, "create_session", lambda *a: None)
    monkeypatch.setattr(routes_module.repository, "save_consent", lambda *a: None)
    return app


def test_create_session_returns_diagnosis_and_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(_awaiting_consent_state())
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post("/session")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_consent"
    assert body["primary_code"] == "order.cost.min"
    assert body["gap"] == "194.11"
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["action_id"] == "a1"


def test_consent_with_unknown_action_id_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(_awaiting_consent_state())
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post("/session/s1/consent", json={"action_id": "does-not-exist"})

    assert response.status_code == 404


def test_consent_when_not_awaiting_consent_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _awaiting_consent_state()
    state["status"] = "reading"
    graph = _FakeGraph(state)
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post("/session/s1/consent", json={"action_id": "a1"})

    assert response.status_code == 409


def test_t18_consent_request_has_no_field_for_a_client_supplied_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A client sending `args_hash`/`state_hash` in the body has nothing
    to overwrite -- `ConsentRequest` only declares `action_id`, and extra
    fields are silently ignored by Pydantic's default config, never
    reaching the server-side hash computation."""
    graph = _FakeGraph(_awaiting_consent_state())
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/session/s1/consent",
        json={
            "action_id": "a1",
            "args_hash": "attacker-supplied-hash",
            "state_hash": "attacker-supplied-hash",
        },
    )

    assert response.status_code == 200
    # The consent actually saved used the server-recomputed hash, not the
    # attacker-supplied one -- verified indirectly: the fake graph's own
    # `aupdate_state` call only ever receives `consent_action_id`.
    assert graph.updated_with == {"consent_action_id": "a1"}


@pytest.mark.parametrize(
    "guard_reason",
    [
        "write refused: state_hash mismatch",
        "write refused: owner mismatch",
        "write refused: consent has expired",
    ],
)
def test_b3_write_guard_refusal_surfaces_as_a_typed_422(
    guard_reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B3: a stale `state_hash` (cart changed), a foreign session/owner,
    and an expired consent are all Write Guard refusals that happen
    *inside* `graph.ainvoke(None, ...)` during resume -- the API surfaces
    every one of them as a typed 422 with the guard's own reason, never a
    200 the client would have to inspect a status field to notice."""
    refused_state = {
        **_awaiting_consent_state(),
        "status": "aborted",
        "error": guard_reason,
    }
    graph = _FakeGraph(_awaiting_consent_state(), resume_state=refused_state)
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post("/session/s1/consent", json={"action_id": "a1"})

    assert response.status_code == 422
    assert guard_reason in response.json()["detail"]


def test_events_stream_emits_consent_required_for_an_awaiting_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(_awaiting_consent_state())
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.get("/session/s1/events")

    assert response.status_code == 200
    assert "event: diagnosis" in response.text
    assert "event: options" in response.text
    assert "event: consent_required" in response.text
    assert '"session_id": "s1"' in response.text


def test_events_stream_emits_error_for_an_aborted_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _awaiting_consent_state()
    state["status"] = "aborted"
    state["error"] = "read failed"
    state["candidates"] = []
    state["diagnosis"] = None
    graph = _FakeGraph(state)
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.get("/session/s1/events")

    assert response.status_code == 200
    assert "event: error" in response.text


def test_auth_routes_are_declared_but_not_implemented_this_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(_awaiting_consent_state())
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    assert client.get("/auth/start").status_code == 501
    assert client.get("/auth/callback").status_code == 501
