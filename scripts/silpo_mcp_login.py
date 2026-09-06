"""One-time interactive Silpo MCP login (D-G3-11): drives a real phone+OTP
OAuth flow in a browser and writes the resulting tokens to
`.cache/silpo_mcp_token.json` via `DiskTokenStorage` — the same file every
other script in this project (`capture_fixture.py`, the future MCP-backed
graph nodes) reads on startup, so this manual step is needed only once while
the refresh token stays valid.

Never imported by application code. `src/lantern/mcp/auth.py`'s own
`redirect_handler`/`callback_handler` always raise, by design, so an
unattended agent process can never open a browser — this script does not
touch those handlers at all. It builds its own `OAuthClientProvider` with
local interactive handlers instead (matching the pattern
`scripts/capture_fixture.py` already uses for constructing a session), never
monkeypatching production code, so nothing in `src/lantern/mcp/` gains an
interactive branch.

Run once, by the project author, from an interactive terminal (the browser
redirect must be pasted back by a human):

    .venv/Scripts/python scripts/silpo_mcp_login.py
"""

from __future__ import annotations

import asyncio
import sys
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.mcp.auth import DEFAULT_TOKEN_PATH, DiskTokenStorage  # noqa: E402

DEFAULT_MCP_URL = "https://mcp.silpo.ua/mcp"

# A lightweight, read-only tool with no required arguments beyond a limit —
# calling it is what forces the OAuth flow to run and gives an observable
# success signal, matching the donor script's own choice of the equivalent
# `silpo_list_branches` call.
LOGIN_PROBE_TOOL = "silpo_list_branches"
LOGIN_PROBE_ARGS = {"limit": 1}


async def _interactive_redirect_handler(authorization_url: str) -> None:
    print("\n1) Opening your browser to log in with your Silpo account...")
    print(f"   If it doesn't open automatically, visit:\n   {authorization_url}\n")
    webbrowser.open(authorization_url)


async def _interactive_callback_handler() -> Tuple[str, Optional[str]]:
    redirect_url = input(
        "2) After logging in, the browser will redirect to a "
        "https://localhost/callback?... URL that will not load — that's "
        "expected. Paste the FULL redirected URL here:\n> "
    ).strip()
    query = urllib.parse.urlparse(redirect_url).query
    params = urllib.parse.parse_qs(query)
    code = params["code"][0]
    state = params.get("state", [None])[0]
    return code, state


async def _login(mcp_url: str) -> int:
    from mcp.client.auth.oauth2 import OAuthClientProvider
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.shared.auth import OAuthClientMetadata
    from pydantic import AnyUrl

    storage = DiskTokenStorage()
    auth = OAuthClientProvider(
        server_url=mcp_url,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[AnyUrl("https://localhost/callback")],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=_interactive_redirect_handler,
        callback_handler=_interactive_callback_handler,
    )

    print(f"Logging in to {mcp_url} ...")
    async with streamablehttp_client(mcp_url, auth=auth) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(LOGIN_PROBE_TOOL, LOGIN_PROBE_ARGS)
            if result.isError:
                print(f"\nLogin call itself failed: {result.content}")
                return 1

    print(f"\nLogin succeeded — {LOGIN_PROBE_TOOL} returned a response.")
    print(f"Token saved to {DEFAULT_TOKEN_PATH}")
    print("scripts/capture_fixture.py can now run without this script.")
    return 0


def main() -> int:
    return asyncio.run(_login(DEFAULT_MCP_URL))


if __name__ == "__main__":
    sys.exit(main())
