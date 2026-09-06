"""B2/B3 (G5+G6 stage spec): the session/consent/events routes, tested
against a FAKE graph (never a real MCP/LLM call, never a real Neon
connection -- `repository.*` functions are monkeypatched, since
`apps.api.routes` calls them as bare module functions).

Rewritten for the live-push design (the author's own call, replacing the
D29 replay-only draft): `POST /session` only creates the session row,
`GET /session/{id}/events` is what actually DRIVES the graph via
`astream(...)` and emits one SSE event per completed node, and
`POST /session/{id}/consent` only records consent -- the write's own
outcome arrives through a SECOND `/events` call.

T18: `ConsentRequest` accepts only `action_id` -- a client-supplied hash
has no field to land in at all, so tampering has nothing to overwrite.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api import routes as routes_module
from src.lantern.domain.models import ActionProposal, Cart, Diagnosis, EvidenceTuple

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


def _diagnosis() -> Diagnosis:
    return Diagnosis(
        blockers=[],
        disclosures=[],
        gap=Decimal("194.11"),
        gap_is_borderline=False,
        primary_code="order.cost.min",
        threshold_source="validation_context",
    )


class _FakeTokenStorage:
    """An authorized guest: `/events` refuses to drive the graph without
    a token for this session (that refusal is its own test below)."""

    def __init__(self, token: object = "a-token") -> None:
        self._token = token

    async def get_tokens(self) -> object:
        return self._token


class _FakeStateSnapshot:
    def __init__(self, values: Dict[str, Any]) -> None:
        self.values = values


class _FakeGraph:
    """Stands in for a compiled `CompiledStateGraph`. `astream` yields
    the chunks a real run would (one `{node: partial}` per completed
    node), then `aget_state` reports the state those chunks add up to --
    the same two-part contract `routes.session_events` consumes.
    """

    def __init__(
        self,
        chunks: List[Dict[str, Any]],
        final_state: Dict[str, Any],
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.chunks = chunks
        self.final_state = final_state
        self.state = initial_state if initial_state is not None else {}
        self.updated_with: Any = None
        self.astream_inputs: List[Any] = []

    async def astream(
        self, input_: Any, config: Any, stream_mode: str = "updates"
    ) -> AsyncIterator[Dict[str, Any]]:
        self.astream_inputs.append(input_)
        for chunk in self.chunks:
            yield chunk
        self.state = self.final_state

    async def aget_state(self, config: Any) -> _FakeStateSnapshot:
        return _FakeStateSnapshot(self.state)

    async def aupdate_state(self, config: Any, values: Any) -> None:
        self.updated_with = values
        self.state = {**self.state, **values}


def _awaiting_consent_state() -> Dict[str, Any]:
    return {
        "session_id": "s1",
        "trace_id": "t1",
        "owner": "owner-hash-1",
        "status": "awaiting_consent",
        "error": None,
        "cart": Cart(cart_id="cart-1", products_total=Decimal("404.89")),
        "diagnosis": _diagnosis(),
        "candidates": [_proposal()],
        "consent_action_id": None,
        "consent": None,
        "receipt": None,
        "write_response": None,
    }


def _read_pipeline_chunks() -> List[Dict[str, Any]]:
    return [
        {"read": {"cart": Cart(cart_id="cart-1", products_total=Decimal("404.89"))}},
        {"diagnose": {"diagnosis": _diagnosis(), "status": "diagnosed"}},
        {"explain": {"candidates": [_proposal()], "status": "awaiting_consent"}},
        {"__interrupt__": ()},
    ]


def _make_app(graph: _FakeGraph, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_module.router)
    app.state.graph_builder = lambda: graph
    app.state.owner_secret = "test-owner-secret"
    app.state.repo_pool = object()
    app.state.version_tuple = {"schema_hash": "h1"}

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


def test_create_session_only_creates_the_session_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The graph does not run here -- `/events` drives it. A `POST` that
    silently blocked on the whole read pipeline is exactly what the live
    push design replaced."""
    graph = _FakeGraph(chunks=[], final_state={})
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post("/session")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["session_id"]
    assert graph.astream_inputs == []  # nothing ran


def test_events_streams_the_read_pipeline_node_by_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=_read_pipeline_chunks(), final_state=_awaiting_consent_state()
    )
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.get("/session/s1/events")

    assert response.status_code == 200
    body = response.text
    assert "event: diagnosis" in body
    assert "event: options" in body
    assert "event: consent_required" in body
    assert '"primary_code": "order.cost.min"' in body
    assert '"gap": "194.11"' in body
    assert '"session_id": "s1"' in body
    # First call for this session: a fresh state was passed, not None.
    assert graph.astream_inputs[0] is not None


def test_events_resumes_an_existing_session_rather_than_restarting_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_state = {
        **_awaiting_consent_state(),
        "status": "verified",
        "receipt": None,
    }
    graph = _FakeGraph(
        chunks=[{"write_and_readback": {"status": "verified"}}],
        final_state=receipt_state,
        initial_state=_awaiting_consent_state(),
    )
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.get("/session/s1/events")

    assert response.status_code == 200
    assert "event: receipt" in response.text
    # A checkpoint already existed -> resumed with None, never re-seeded.
    assert graph.astream_inputs == [None]


def test_events_emits_error_when_a_node_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aborted = {**_awaiting_consent_state(), "status": "aborted", "error": "read failed"}
    graph = _FakeGraph(
        chunks=[{"read": {"status": "aborted", "error": "read failed"}}],
        final_state=aborted,
    )
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.get("/session/s1/events")

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "read failed" in response.text


def test_events_for_an_unknown_session_is_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(chunks=[], final_state={})
    app = _make_app(graph, monkeypatch)
    monkeypatch.setattr(routes_module.repository, "get_session", lambda *a: None)
    client = TestClient(app)

    response = client.get("/session/nope/events")

    assert response.status_code == 404


def test_consent_records_and_advances_without_running_the_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=[], final_state={}, initial_state=_awaiting_consent_state()
    )
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post("/session/s1/consent", json={"action_id": "a1"})

    assert response.status_code == 200
    assert response.json()["status"] == "consent_recorded"
    assert graph.updated_with == {"consent_action_id": "a1"}
    assert graph.astream_inputs == []  # the write runs on the next /events call


def test_consent_with_unknown_action_id_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=[], final_state={}, initial_state=_awaiting_consent_state()
    )
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post("/session/s1/consent", json={"action_id": "does-not-exist"})

    assert response.status_code == 404


def test_consent_when_not_awaiting_consent_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {**_awaiting_consent_state(), "status": "reading"}
    graph = _FakeGraph(chunks=[], final_state={}, initial_state=state)
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post("/session/s1/consent", json={"action_id": "a1"})

    assert response.status_code == 409


def test_consent_for_an_unknown_session_is_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(chunks=[], final_state={}, initial_state={})
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.post("/session/nope/consent", json={"action_id": "a1"})

    assert response.status_code == 404


def test_t18_consent_request_has_no_field_for_a_client_supplied_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A client sending `args_hash`/`state_hash` in the body has nothing
    to overwrite -- `ConsentRequest` only declares `action_id`, and extra
    fields never reach the server-side hash computation."""
    graph = _FakeGraph(
        chunks=[], final_state={}, initial_state=_awaiting_consent_state()
    )
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
    assert graph.updated_with == {"consent_action_id": "a1"}


@pytest.mark.parametrize(
    "guard_reason",
    [
        "write refused: state_hash mismatch",
        "write refused: owner mismatch",
        "write refused: consent has expired",
    ],
)
def test_b3_write_guard_refusal_reaches_the_client_as_an_error_event(
    guard_reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B3: a stale `state_hash`, a foreign owner and an expired consent
    are all Write Guard refusals raised inside the resumed graph -- with
    live push they surface as the plan's own `error` SSE event carrying
    the guard's stated reason, not as a silent 200."""
    refused = {
        **_awaiting_consent_state(),
        "status": "aborted",
        "error": guard_reason,
    }
    graph = _FakeGraph(
        chunks=[{"write_guard": {"status": "aborted", "error": guard_reason}}],
        final_state=refused,
        initial_state=_awaiting_consent_state(),
    )
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    response = client.get("/session/s1/events")

    assert response.status_code == 200
    assert "event: error" in response.text
    assert guard_reason in response.text


def test_events_refuses_an_unauthorized_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No guest token for this session -> 401 with the login URL, and the
    graph is never driven. Without this check the run would fall through
    to the single operator token on disk and read the WRONG cart -- the
    exact failure per-session storage exists to prevent."""
    graph = _FakeGraph(chunks=_read_pipeline_chunks(), final_state={})
    app = _make_app(graph, monkeypatch)

    class _Unauthorized:
        async def get_tokens(self) -> object:
            return None

    monkeypatch.setattr(
        routes_module, "SessionTokenStorage", lambda pool, sid: _Unauthorized()
    )
    client = TestClient(app)

    response = client.get("/session/s1/events")

    assert response.status_code == 401
    assert "/auth/start" in response.json()["detail"]
    assert graph.astream_inputs == []  # the graph never ran


def test_create_session_points_the_client_at_the_login_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(chunks=[], final_state={})
    app = _make_app(graph, monkeypatch)
    client = TestClient(app)

    body = client.post("/session").json()

    assert body["authorized"] is False
    assert body["auth_url"] == f"/auth/start?session_id={body['session_id']}"
