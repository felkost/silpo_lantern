"""the session id is an `HttpOnly; Secure;
SameSite=Lax` cookie, never a URL. Before this the id was a bearer
capability riding in `/auth/start?session_id=...` -- browser history, a
projector at a demo -- and the only check on `/events` and `/consent` was
that a token row existed for whatever id the path carried.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api import routes as routes_module
from apps.api.session_cookie import SESSION_COOKIE
from tests.unit.test_api_session_routes import (
    _awaiting_consent_state,
    _FakeGraph,
    _make_app,
    _read_pipeline_chunks,
)


def _client(monkeypatch: pytest.MonkeyPatch, graph: Any = None) -> TestClient:
    graph = graph or _FakeGraph(chunks=[], final_state={})
    # `https`: the cookie is `Secure`, and httpx's jar refuses to send a
    # Secure cookie over plain http -- exactly what a browser does.
    return TestClient(_make_app(graph, monkeypatch), base_url="https://testserver")


def test_create_session_sets_the_cookie_and_keeps_the_id_out_of_the_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)

    response = client.post("/session")

    body = response.json()
    header = response.headers["set-cookie"]
    assert f"{SESSION_COOKIE}={body['session_id']}" in header
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header.replace("SameSite=Lax", "SameSite=lax")
    assert body["auth_url"] == "/auth/start"
    assert body["session_id"] not in body["auth_url"]


def test_events_refuses_a_path_id_the_cookie_does_not_vouch_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leaked id is worthless on its own: the path must match the
    cookie the same browser holds."""
    graph = _FakeGraph(
        chunks=_read_pipeline_chunks(), final_state=_awaiting_consent_state()
    )
    client = _client(monkeypatch, graph)

    assert client.get("/session/s1/events").status_code == 401
    client.cookies.set(SESSION_COOKIE, "someone-else")
    assert client.get("/session/s1/events").status_code == 401
    assert graph.astream_inputs == []  # nothing ran

    client.cookies.set(SESSION_COOKIE, "s1")
    assert client.get("/session/s1/events").status_code == 200


def test_consent_refuses_without_the_matching_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=[], final_state={}, initial_state=_awaiting_consent_state()
    )
    client = _client(monkeypatch, graph)

    response = client.post("/session/s1/consent", json={"action_id": "a1"})

    assert response.status_code == 401
    assert graph.updated_with is None


def test_no_route_echoes_the_session_id_into_a_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """the unauthorized-yet 401 used to spell out
    `/auth/start?session_id=...` in its detail."""
    client = _client(monkeypatch)
    monkeypatch.setattr(
        routes_module, "SessionTokenStorage", lambda pool, sid: _NoToken()
    )
    client.cookies.set(SESSION_COOKIE, "s1")

    response = client.get("/session/s1/events")

    assert response.status_code == 401
    assert "s1" not in response.json()["detail"]


class _NoToken:
    async def get_tokens(self) -> None:
        return None


def test_delete_session_removes_the_credential_and_clears_the_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """logout deletes the `oauth_tokens` row -- the credential
    -- and a following `/events` is refused. The `sessions` row stays:
    `consents`/`receipts` reference it WITHOUT cascade (0003, 0005), so
    deleting it would either fail on the FK or destroy the audit trail."""
    deleted: list = []
    client = _client(monkeypatch)
    monkeypatch.setattr(
        routes_module.repository,
        "delete_session_token",
        lambda pool, sid: deleted.append(sid),
    )
    client.cookies.set(SESSION_COOKIE, "s1")

    response = client.delete("/session/s1")

    assert response.status_code == 204
    assert deleted == ["s1"]
    assert f"{SESSION_COOKIE}=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"] or "expires" in (
        response.headers["set-cookie"].lower()
    )
    monkeypatch.setattr(
        routes_module, "SessionTokenStorage", lambda pool, sid: _NoToken()
    )
    client.cookies.set(SESSION_COOKIE, "s1")
    assert client.get("/session/s1/events").status_code == 401


def test_delete_session_needs_the_matching_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(
        routes_module.repository,
        "delete_session_token",
        lambda pool, sid: pytest.fail("must not delete"),
    )

    assert client.delete("/session/s1").status_code == 401


def test_restart_moves_the_credential_to_a_new_session_and_re_points_the_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Перевірити знову»: one run is one session, so a second check is a
    second session -- with the SAME login. The credential moves, the old
    session keeps its audit rows, and the cookie now names the new id, so
    the next `/events` is a fresh graph start for this guest."""
    created: list = []
    moved: list = []
    client = _client(monkeypatch)
    monkeypatch.setattr(
        routes_module.repository,
        "create_session",
        lambda pool, sid, tid, owner: created.append(sid),
    )
    monkeypatch.setattr(
        routes_module.repository,
        "move_session_token",
        lambda pool, old, new: moved.append((old, new)) or True,
    )
    client.cookies.set(SESSION_COOKIE, "s1")

    response = client.post("/session/s1/restart")

    assert response.status_code == 200
    body = response.json()
    assert body["authorized"] is True and body["auth_url"] == ""
    assert created == [body["session_id"]] and body["session_id"] != "s1"
    assert moved == [("s1", body["session_id"])]
    assert f"{SESSION_COOKIE}={body['session_id']}" in response.headers["set-cookie"]


def test_restart_without_a_live_login_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(
        routes_module.repository, "create_session", lambda pool, sid, tid, owner: None
    )
    monkeypatch.setattr(
        routes_module.repository, "move_session_token", lambda pool, old, new: False
    )
    client.cookies.set(SESSION_COOKIE, "s1")

    assert client.post("/session/s1/restart").status_code == 401
    # and without the matching cookie the route never reaches the repository
    client.cookies.clear()
    monkeypatch.setattr(
        routes_module.repository,
        "move_session_token",
        lambda pool, old, new: pytest.fail("must not move"),
    )
    assert client.post("/session/s1/restart").status_code == 401
