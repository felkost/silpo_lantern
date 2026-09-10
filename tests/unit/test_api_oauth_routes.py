"""`/auth/start` and `/auth/callback` (`apps/api/oauth_routes.py`): the
two-phase authorization-code+PKCE flow, per guest, tested entirely
offline -- the SDK's own metadata discovery and token exchange are
mocked at the `httpx` boundary and the per-session storage is
substituted, so no live Silpo OAuth server and no real token file are
ever touched.

What these tests deliberately do NOT prove: that Silpo's real
authorization server accepts the resulting redirect. That needs a human
completing Silpo's own login in a real browser (the exact step
`CLAUDE.md` forbids an agent from driving), and an OAuth client whose
registered `redirect_uri` actually points at this app's `/auth/callback`
-- an operator decision with an external effect on Silpo's own server.
"""

import time
from typing import Any, Dict, Optional

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from pydantic import AnyUrl

from apps.api import oauth_routes
from apps.api.session_cookie import SESSION_COOKIE

_AUTH_ENDPOINT = "https://auth.example.test/authorize"
_SESSION_ID = "11111111-1111-1111-1111-111111111111"
_TOKEN_ENDPOINT = "https://auth.example.test/token"
_REDIRECT_URI = "https://localhost/callback"


def _client_info() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="client-abc",
        redirect_uris=[AnyUrl(_REDIRECT_URI)],
        token_endpoint_auth_method="none",
    )


def _metadata() -> OAuthMetadata:
    return OAuthMetadata(
        issuer=AnyUrl("https://auth.example.test"),
        authorization_endpoint=AnyUrl(_AUTH_ENDPOINT),
        token_endpoint=AnyUrl(_TOKEN_ENDPOINT),
        response_types_supported=["code"],
    )


class _FakeStorage:
    """Stands in for `DiskTokenStorage` -- never touches
    `.cache/silpo_mcp_token.json`."""

    def __init__(self, client_info: Optional[OAuthClientInformationFull]) -> None:
        self._client_info = client_info
        self.stored_token: Optional[OAuthToken] = None

    async def get_client_info(self) -> Optional[OAuthClientInformationFull]:
        return self._client_info

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.stored_token = tokens

    async def get_tokens(self) -> Optional[OAuthToken]:
        return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info = client_info


def _client(app: FastAPI, session_id: str = _SESSION_ID) -> TestClient:
    """G10 (A-G10-04): `/auth/start` reads the session from the cookie
    `POST /session` set, never from the URL."""
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, session_id)
    return client


def _make_app(
    monkeypatch: pytest.MonkeyPatch,
    storage: _FakeStorage,
    *,
    token_response: Optional[httpx.Response] = None,
    session_exists: bool = True,
) -> FastAPI:
    app = FastAPI()
    app.include_router(oauth_routes.router)
    app.state.oauth_pending = {}
    app.state.repo_pool = object()

    # Per-session storage: the route asks for one keyed by session_id,
    # and every test here uses the same fake behind it.
    monkeypatch.setattr(
        oauth_routes, "_storage_for", lambda request, session_id: storage
    )
    monkeypatch.setattr(
        oauth_routes.repository,
        "get_session",
        lambda *a: (
            {"session_id": _SESSION_ID, "owner": "o"} if session_exists else None
        ),
    )

    async def fake_discover(server_url: str) -> OAuthMetadata:
        return _metadata()

    monkeypatch.setattr(oauth_routes, "_discover_oauth_metadata", fake_discover)

    if token_response is not None:

        async def fake_post(self: Any, url: str, **kwargs: Any) -> httpx.Response:
            return token_response

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    return app


def test_auth_start_redirects_with_pkce_and_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(_client_info())
    app = _make_app(monkeypatch, storage)
    client = _client(app)

    response = client.get("/auth/start", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith(_AUTH_ENDPOINT)
    assert "code_challenge=" in location
    assert "code_challenge_method=S256" in location
    assert "response_type=code" in location
    assert "client_id=client-abc" in location
    # The PKCE verifier stayed server-side -- only the challenge is sent.
    assert "code_verifier" not in location
    assert len(app.state.oauth_pending) == 1


def test_auth_start_without_a_registered_client_is_501(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(None)
    app = _make_app(monkeypatch, storage)
    client = _client(app)

    response = client.get("/auth/start", follow_redirects=False)

    assert response.status_code == 501
    assert "register" in response.json()["detail"].lower()


def test_auth_callback_exchanges_the_code_and_stores_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(_client_info())
    token_response = httpx.Response(
        200,
        json={
            "access_token": "the-new-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
        request=httpx.Request("POST", _TOKEN_ENDPOINT),
    )
    app = _make_app(monkeypatch, storage, token_response=token_response)
    client = _client(app)

    # Phase 1 seeds the pending state the callback must match.
    client.get("/auth/start", follow_redirects=False)
    state = next(iter(app.state.oauth_pending))

    response = client.get(
        f"/auth/callback?code=the-code&state={state}", follow_redirects=False
    )

    # G10 (D87): the guest lands back on the app, not on a JSON page with
    # no way forward -- and on a BARE `/`: the session id never rides in
    # a redirect target (G10-5).
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert storage.stored_token is not None
    assert storage.stored_token.access_token == "the-new-access-token"
    # The pending entry is consumed -- a replayed callback cannot reuse it.
    assert app.state.oauth_pending == {}


def test_auth_callback_with_an_unknown_state_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CSRF protection: a callback whose `state` this server never issued
    has no PKCE verifier to pair with and is rejected before any token
    exchange is attempted."""
    storage = _FakeStorage(_client_info())
    app = _make_app(monkeypatch, storage)
    client = _client(app)

    response = client.get("/auth/callback?code=the-code&state=never-issued")

    assert response.status_code == 400
    assert "csrf" in response.json()["detail"].lower()
    assert storage.stored_token is None


def test_auth_callback_rejects_a_replayed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(_client_info())
    token_response = httpx.Response(
        200,
        json={"access_token": "t", "token_type": "Bearer"},
        request=httpx.Request("POST", _TOKEN_ENDPOINT),
    )
    app = _make_app(monkeypatch, storage, token_response=token_response)
    client = _client(app)
    client.get("/auth/start", follow_redirects=False)
    state = next(iter(app.state.oauth_pending))

    first = client.get(f"/auth/callback?code=c1&state={state}", follow_redirects=False)
    second = client.get(f"/auth/callback?code=c1&state={state}")

    assert first.status_code == 303
    assert second.status_code == 400


def test_auth_callback_rejects_an_expired_pending_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(_client_info())
    app = _make_app(monkeypatch, storage)
    client = _client(app)
    client.get("/auth/start", follow_redirects=False)
    state = next(iter(app.state.oauth_pending))
    app.state.oauth_pending[state]["created_at"] = (
        time.time() - oauth_routes.PENDING_TTL_SECONDS - 1
    )

    response = client.get(f"/auth/callback?code=c1&state={state}")

    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_auth_callback_surfaces_an_authorization_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(_client_info())
    app = _make_app(monkeypatch, storage)
    client = _client(app)

    response = client.get("/auth/callback?error=access_denied")

    assert response.status_code == 400
    assert "access_denied" in response.json()["detail"]


def test_auth_callback_without_code_or_state_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(_client_info())
    app = _make_app(monkeypatch, storage)
    client = _client(app)

    response = client.get("/auth/callback")

    assert response.status_code == 400


def test_pending_store_holds_the_verifier_not_the_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verifier is the secret half of PKCE -- it must stay on the
    server and never appear in the redirect the browser follows."""
    storage = _FakeStorage(_client_info())
    app = _make_app(monkeypatch, storage)
    client = _client(app)

    response = client.get("/auth/start", follow_redirects=False)
    pending: Dict[str, Any] = next(iter(app.state.oauth_pending.values()))

    assert "code_verifier" in pending
    assert pending["code_verifier"] not in response.headers["location"]


def test_two_guests_get_two_separate_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole reason per-session storage exists: before it, a second
    guest completing the flow overwrote the first one's token in the
    single shared file, and both then read the same cart."""
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    per_session: Dict[str, _FakeStorage] = {
        session_a: _FakeStorage(_client_info()),
        session_b: _FakeStorage(_client_info()),
    }
    issued = iter(["token-for-guest-A", "token-for-guest-B"])

    app = FastAPI()
    app.include_router(oauth_routes.router)
    app.state.oauth_pending = {}
    app.state.repo_pool = object()
    monkeypatch.setattr(
        oauth_routes,
        "_storage_for",
        lambda request, session_id: per_session[session_id],
    )
    monkeypatch.setattr(
        oauth_routes.repository, "get_session", lambda *a: {"owner": "o"}
    )

    async def fake_discover(server_url: str) -> OAuthMetadata:
        return _metadata()

    monkeypatch.setattr(oauth_routes, "_discover_oauth_metadata", fake_discover)

    async def fake_post(self: Any, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": next(issued), "token_type": "Bearer"},
            request=httpx.Request("POST", _TOKEN_ENDPOINT),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = _client(app)

    for session_id in (session_a, session_b):
        client.cookies.set(SESSION_COOKIE, session_id)
        client.get("/auth/start", follow_redirects=False)
    states = list(app.state.oauth_pending)
    for state in states:
        client.get(f"/auth/callback?code=c&state={state}")

    token_a = per_session[session_a].stored_token
    token_b = per_session[session_b].stored_token
    assert token_a is not None and token_b is not None
    assert token_a.access_token != token_b.access_token


def test_callback_stores_against_the_session_that_started_the_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The session comes from the SERVER-held pending entry, never from a
    query parameter -- a callback URL cannot be edited to redirect
    somebody else's token into your own session."""
    storage = _FakeStorage(_client_info())
    captured: Dict[str, str] = {}

    app = FastAPI()
    app.include_router(oauth_routes.router)
    app.state.oauth_pending = {}
    app.state.repo_pool = object()

    def _storage_for(request: Any, session_id: str) -> _FakeStorage:
        captured["session_id"] = session_id
        return storage

    monkeypatch.setattr(oauth_routes, "_storage_for", _storage_for)
    monkeypatch.setattr(
        oauth_routes.repository, "get_session", lambda *a: {"owner": "o"}
    )

    async def fake_discover(server_url: str) -> OAuthMetadata:
        return _metadata()

    monkeypatch.setattr(oauth_routes, "_discover_oauth_metadata", fake_discover)

    async def fake_post(self: Any, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "t", "token_type": "Bearer"},
            request=httpx.Request("POST", _TOKEN_ENDPOINT),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = _client(app)

    client.get("/auth/start", follow_redirects=False)
    state = next(iter(app.state.oauth_pending))
    captured.clear()
    client.get(f"/auth/callback?code=c&state={state}&session_id=attacker-session")

    assert captured["session_id"] == _SESSION_ID


def test_auth_start_without_a_cookie_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """G10 (A-G10-04): a `session_id` query parameter is no longer read at
    all -- the id must not be placeable in a URL."""
    app = _make_app(monkeypatch, _FakeStorage(_client_info()))
    client = TestClient(app)

    response = client.get(f"/auth/start?session_id={_SESSION_ID}")

    assert response.status_code == 401
    assert app.state.oauth_pending == {}
