"""Live, two-phase Silpo MCP OAuth for a human operator's own browser --
`/auth/start` redirects to Silpo's real authorization endpoint,
`/auth/callback` completes the authorization-code+PKCE exchange and
persists the resulting token via the same `DiskTokenStorage`
`scripts/silpo_mcp_login.py` already writes to.

Reuses the MCP SDK's own metadata-discovery and token/registration-
response parsing helpers (`mcp.client.auth.oauth2`) rather than
reimplementing PKCE or response parsing by hand. `OAuthClientProvider`
itself cannot be reused directly for the split: its authorization-code
grant is one inline async generator method (its own source comment,
confirmed by reading it: "OAuth flow must be inline due to generator
constraints") -- it builds the authorize URL, awaits a redirect handler,
then awaits a callback handler, all within one continuous async call,
with no exposed point to suspend and resume from a second, independent
HTTP request. This module builds the authorize URL and the token
exchange request the same way `OAuthClientProvider._perform_
authorization_code_grant`/`_exchange_token_authorization_code` do
(read directly from their source), but as two separately callable route
handlers, correlated by a server-held `state` -> PKCE verifier mapping.

Requires an OAuth client already registered with a `redirect_uri` that
resolves to THIS app's own `/auth/callback` -- NOT the
`https://localhost/callback` placeholder `scripts/silpo_mcp_login.py`
registers for its own local-catcher flow. Registering a new client (or
confirming an existing one's `redirect_uri` covers this app's deployed
callback URL) is an operator decision with a real, external effect on
Silpo's own authorization server; this module never does it silently --
`/auth/start` fails loudly (501) if no matching client is on disk.

Single-worker assumption, same one `mcp.client.ToolRegistry`'s own
docstring already states for this project: `app.state.oauth_pending` is
an in-process dict, not shared across worker processes.
"""

import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

# These four helpers exist and are stable in the installed SDK (measured
# directly, not assumed) but are not in `mcp.client.auth.oauth2`'s own
# declared re-export surface -- mypy strict's `no_implicit_reexport`
# flags the import, not a real type error, matching this project's
# existing pattern for the same class of SDK friction (see
# `graph/build.py`'s `_add_node`).
from mcp.client.auth.oauth2 import (  # type: ignore[attr-defined]
    OAuthContext,
    OAuthFlowError,
    PKCEParameters,
    build_oauth_authorization_server_metadata_discovery_urls,
    create_oauth_metadata_request,
    handle_auth_metadata_response,
    handle_token_response_scopes,
)
from mcp.shared.auth import OAuthClientMetadata, OAuthMetadata
from pydantic import AnyUrl

from apps.api.session_cookie import cookie_session_id
from src.lantern.mcp.session import DEFAULT_MCP_URL
from src.lantern.mcp.session_token_storage import SessionTokenStorage
from src.lantern.memory import repository

router = APIRouter()

# Generous: a human must load Silpo's own login page, possibly complete
# an OTP challenge, before returning here -- not a machine-speed step.
PENDING_TTL_SECONDS = 600.0


async def _discover_oauth_metadata(server_url: str) -> OAuthMetadata:
    """The metadata-discovery half of `OAuthClientProvider._initialize`
    -- the only half this module needs, since client registration is
    assumed already done (see module docstring). Reuses the SDK's own
    request-building and response-parsing, never re-derives the
    well-known discovery URL shape by hand."""
    urls = build_oauth_authorization_server_metadata_discovery_urls(None, server_url)
    async with httpx.AsyncClient() as client:
        for url in urls:
            request = create_oauth_metadata_request(url)
            response = await client.send(request)
            should_retry, metadata = await handle_auth_metadata_response(response)
            if metadata is not None:
                return metadata
            if not should_retry:
                break
    raise OAuthFlowError(
        f"could not discover OAuth authorization server metadata for {server_url}"
    )


def _storage_for(request: Request, session_id: str) -> SessionTokenStorage:
    return SessionTokenStorage(request.app.state.repo_pool, session_id)


@router.get("/auth/start")
async def auth_start(request: Request) -> RedirectResponse:
    """Sends THIS guest to Silpo's own login (phone + OTP). The session
    comes from the cookie `POST /session` set (G10, A-G10-04) -- never from
    the URL, which the browser records -- because the token that comes
    back belongs to one guest, and the callback has to know whose session
    to store it against."""
    session_id = cookie_session_id(request)
    if repository.get_session(request.app.state.repo_pool, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    storage = _storage_for(request, session_id)
    client_info = await storage.get_client_info()
    if (
        client_info is None
        or not client_info.redirect_uris
        or not client_info.client_id
    ):
        raise HTTPException(
            status_code=501,
            detail=(
                "No app-level OAuth client registered. Run "
                "scripts/g5_register_oauth_client.py once, with a "
                "--redirect-uri matching this app's own /auth/callback."
            ),
        )

    try:
        metadata = await _discover_oauth_metadata(DEFAULT_MCP_URL)
    except OAuthFlowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if metadata.authorization_endpoint is None:
        raise HTTPException(
            status_code=502, detail="server metadata has no authorization_endpoint"
        )

    pkce = PKCEParameters.generate()
    state = secrets.token_urlsafe(32)
    request.app.state.oauth_pending[state] = {
        "code_verifier": pkce.code_verifier,
        "session_id": session_id,
        "created_at": time.time(),
    }

    redirect_uri = str(client_info.redirect_uris[0])
    params = {
        "response_type": "code",
        "client_id": client_info.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": "S256",
    }
    return RedirectResponse(f"{metadata.authorization_endpoint}?{urlencode(params)}")


@router.get("/auth/callback")
async def auth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
) -> RedirectResponse:
    if error:
        raise HTTPException(
            status_code=400, detail=f"authorization server returned error: {error}"
        )
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code or state")

    pending: Optional[Dict[str, Any]] = request.app.state.oauth_pending.pop(state, None)
    if pending is None:
        raise HTTPException(
            status_code=400, detail="unknown or expired state (possible CSRF)"
        )
    if time.time() - pending["created_at"] > PENDING_TTL_SECONDS:
        raise HTTPException(
            status_code=400, detail="authorization flow expired, restart"
        )

    # The token about to be issued belongs to the guest whose session
    # started THIS flow -- read from the server-held pending entry, never
    # from a query parameter the browser could have been redirected with.
    storage = _storage_for(request, pending["session_id"])
    client_info = await storage.get_client_info()
    if (
        client_info is None
        or not client_info.redirect_uris
        or not client_info.client_id
    ):
        raise HTTPException(
            status_code=500, detail="client registration disappeared mid-flow"
        )

    try:
        metadata = await _discover_oauth_metadata(DEFAULT_MCP_URL)
    except OAuthFlowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if metadata.token_endpoint is None:
        raise HTTPException(
            status_code=502, detail="server metadata has no token_endpoint"
        )

    # Same field shape as `OAuthClientProvider._exchange_token_authorization_code`
    # (read directly from its source, not guessed).
    token_data: Dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": str(client_info.redirect_uris[0]),
        "client_id": client_info.client_id,
        "code_verifier": pending["code_verifier"],
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    context = OAuthContext(
        server_url=DEFAULT_MCP_URL,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[AnyUrl(str(u)) for u in client_info.redirect_uris],
            token_endpoint_auth_method=client_info.token_endpoint_auth_method or "none",
        ),
        storage=storage,
        redirect_handler=None,
        callback_handler=None,
        client_info=client_info,
    )
    token_data_final, headers = context.prepare_token_auth(token_data, headers)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            str(metadata.token_endpoint), data=token_data_final, headers=headers
        )
    try:
        token = await handle_token_response_scopes(response)
    except Exception as exc:  # SDK raises its own OAuthTokenError/ValidationError
        raise HTTPException(
            status_code=502, detail=f"token exchange failed: {exc}"
        ) from exc

    await storage.set_tokens(token)
    # G10 (D87): back to the app, on a BARE `/`. The session was resolved
    # from the server-held `state` above, so the id never needed to ride
    # in the redirect target -- and must not (G10-5: browser history, a
    # projector at a demo). The SPA finds its own copy in `sessionStorage`.
    return RedirectResponse("/", status_code=303)
