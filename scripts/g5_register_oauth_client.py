"""Registers an OAuth client whose `redirect_uri` points at THIS app's own
`/auth/callback`, so `apps/api/oauth_routes.py`'s two-phase browser flow
can actually be used against the live server.

Why a new registration rather than reusing the one on disk: the existing
`.cache/silpo_mcp_token.json` client was registered by
`scripts/silpo_mcp_login.py` with `redirect_uris:
["https://localhost/callback"]` -- that script's own local-catcher
placeholder. An OAuth server only redirects to a URI the client is
registered for, so that registration can never serve this app's HTTP
callback route. Measured live (2026-09-07): `https://mcp.silpo.ua`
advertises `registration_endpoint: https://mcp.silpo.ua/register`,
`code_challenge_methods_supported: ["plain", "S256"]` and
`grant_types_supported: ["authorization_code", "refresh_token"]`, so
dynamic client registration (RFC 7591) is available for exactly this.

Writes to its OWN file (`.cache/silpo_mcp_web_client.json`), never
overwriting `.cache/silpo_mcp_token.json` -- that file holds a WORKING
token issued to the OLD client_id, and clobbering its `client_info`
would leave a token and a registration that no longer match.

This creates a real registration on Silpo's own authorization server.
It is read-write against an external system, so it is author-run, never
self-initiated -- same rule as a live cart write.

Usage (local dev default):
    .venv/Scripts/python.exe scripts/g5_register_oauth_client.py

Explicit callback (deployed):
    .venv/Scripts/python.exe scripts/g5_register_oauth_client.py \
        --redirect-uri https://lantern.example.com/auth/callback
"""

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.client.auth.oauth2 import (  # noqa: E402
    build_oauth_authorization_server_metadata_discovery_urls,
    create_client_registration_request,
    create_oauth_metadata_request,
    handle_auth_metadata_response,
    handle_registration_response,
)
from mcp.shared.auth import OAuthClientMetadata  # noqa: E402
from pydantic import AnyUrl  # noqa: E402

from src.lantern.config import PROJECT_ROOT  # noqa: E402
from src.lantern.mcp.session import DEFAULT_MCP_URL  # noqa: E402

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8000/auth/callback"
WEB_CLIENT_PATH = PROJECT_ROOT / ".cache" / "silpo_mcp_web_client.json"


async def _register(redirect_uri: str, server_url: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        metadata = None
        for url in build_oauth_authorization_server_metadata_discovery_urls(
            None, server_url
        ):
            response = await client.send(create_oauth_metadata_request(url))
            _, metadata = await handle_auth_metadata_response(response)
            if metadata is not None:
                break
        if metadata is None:
            raise SystemExit(f"could not discover OAuth metadata for {server_url}")
        print(f"registration_endpoint: {metadata.registration_endpoint}")

        client_metadata = OAuthClientMetadata(
            redirect_uris=[AnyUrl(redirect_uri)],
            # Public client: PKCE is the protection, no client_secret to
            # leak. The server advertises "none" as a supported method
            # and the existing CLI registration already uses it.
            token_endpoint_auth_method="none",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            client_name="Lantern recovery card",
        )
        parsed = urlparse(server_url)
        auth_base_url = f"{parsed.scheme}://{parsed.netloc}"
        request = create_client_registration_request(
            metadata, client_metadata, auth_base_url
        )
        response = await client.send(request)
        info = await handle_registration_response(response)

    WEB_CLIENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_CLIENT_PATH.write_text(
        info.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )
    print(f"registered client_id: {info.client_id}")
    print(f"redirect_uris: {[str(u) for u in (info.redirect_uris or [])]}")
    print(f"written to: {WEB_CLIENT_PATH}")
    print(
        "\nThis file is gitignored (.cache/). It holds a client_id, not a "
        "guest's token -- but treat it as a credential anyway."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI)
    parser.add_argument("--server-url", default=DEFAULT_MCP_URL)
    args = parser.parse_args()

    print(f"Registering a client for redirect_uri: {args.redirect_uri}")
    print(f"Authorization server derived from: {args.server_url}\n")
    asyncio.run(_register(args.redirect_uri, args.server_url))


if __name__ == "__main__":
    main()
