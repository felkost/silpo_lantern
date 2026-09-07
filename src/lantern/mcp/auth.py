"""Silpo MCP OAuth: persistent token storage and the manual-login contract.
Ported from the donor project's `silpo_mcp_auth.py` — SDK reconnaissance
confirmed `TokenStorage` is still a structural `typing.Protocol` with the
same four async methods in the installed `mcp==1.29.0`, no adaptation
needed on the port itself.

`build_redirect_handler` is new: the donor's `redirect_handler` always
raised the same `SilpoMcpAuthRequiredError`, whether or not a token had
ever existed. A previously-valid token being rejected mid-session is a
different, previously-unflagged failure — it must surface distinctly
rather than as an opaque "never logged in" during a live demo.
"""

import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from src.lantern.config import PROJECT_ROOT
from src.lantern.mcp.errors import McpAuthExpiredError

DEFAULT_TOKEN_PATH = PROJECT_ROOT / ".cache" / "silpo_mcp_token.json"

# The APP-level OAuth client registration (one per application, shared by
# every guest -- distinct from a guest's own token, which is per session).
# Written by `scripts/g5_register_oauth_client.py`, whose registration
# carries a `redirect_uri` pointing at this app's own `/auth/callback`;
# `DEFAULT_TOKEN_PATH`'s own client was registered by the CLI login script
# for `https://localhost/callback` and cannot serve an HTTP callback route.
#
# G7 (IV-07): `SILPO_MCP_WEB_CLIENT_PATH` overrides the default local-dev
# path -- Render's free tier has no persistent disk, so a file written at
# one deploy does not survive the next; its "Secret Files" feature always
# mounts a file at `/etc/secrets/<filename>` (no subdirectories in the
# filename Render accepts), never at an arbitrary repo-relative path like
# `.cache/...`. Set this env var to that mounted path on a deployed host;
# local dev leaves it unset and gets the `.cache/` default unchanged.
WEB_CLIENT_PATH = Path(
    os.environ.get(
        "SILPO_MCP_WEB_CLIENT_PATH",
        str(PROJECT_ROOT / ".cache" / "silpo_mcp_web_client.json"),
    )
)


class TokenStorageLike(Protocol):
    """Structural type for the SDK's own `TokenStorage` protocol -- what
    `DiskTokenStorage` (one operator, one file) and
    `SessionTokenStorage` (one guest, one Neon row) both satisfy. Defined
    here, beside the storages themselves, so `session.py` and
    `build_redirect_handler` share one definition instead of two that
    could drift."""

    async def get_tokens(self) -> Any: ...  # noqa: E704

    async def set_tokens(self, tokens: Any) -> None: ...  # noqa: E704

    async def get_client_info(self) -> Any: ...  # noqa: E704

    async def set_client_info(self, client_info: Any) -> None: ...  # noqa: E704


class SilpoMcpAuthRequiredError(Exception):
    """No valid token on disk and no automated login exists — Silpo's OAuth
    is phone+OTP against a real account, so this fails loudly rather than
    attempting to open a browser from inside an unattended agent process.
    """


class DiskTokenStorage:
    """`mcp.client.auth.oauth2.TokenStorage` implementation backed by one
    JSON file. Never logged, never traced — `.cache/` is gitignored.

    Implements `TokenStorage`'s four async methods structurally (it is a
    `Protocol`, not an ABC — no inheritance declared, matching the installed
    SDK's own pattern).
    """

    def __init__(self, path: Path = DEFAULT_TOKEN_PATH) -> None:
        self._path = path

    def _read(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {}
        result: Dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
        return result

    def _write(self, data: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data), encoding="utf-8")

    async def get_tokens(self) -> Optional[OAuthToken]:
        raw = self._read().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        data["tokens"] = json.loads(tokens.model_dump_json())
        self._write(data)

    async def get_client_info(self) -> Optional[OAuthClientInformationFull]:
        raw = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client_info"] = json.loads(client_info.model_dump_json())
        self._write(data)


def build_redirect_handler(
    storage: TokenStorageLike,
) -> Callable[[str], Awaitable[None]]:
    """Distinguish "never logged in" from "was logged in, now rejected"
    using one measurable fact — whether a token was ever written to this
    storage — rather than an invented behavioural signal from the OAuth
    flow itself.
    """

    async def redirect_handler(authorization_url: str) -> None:
        if await storage.get_tokens() is not None:
            raise McpAuthExpiredError(
                "A previously-valid Silpo MCP token was rejected — a human "
                "must complete the phone+OTP login again. Authorization "
                f"URL: {authorization_url}"
            )
        raise SilpoMcpAuthRequiredError(
            "No valid Silpo MCP token on disk. A human must complete the "
            "phone+OTP login once — authorization URL: "
            f"{authorization_url}"
        )

    return redirect_handler


async def callback_handler() -> "tuple[str, Optional[str]]":
    """Raises — see `build_redirect_handler`; this is the other half of the
    same manual-login contract `OAuthClientProvider` requires.
    """
    raise SilpoMcpAuthRequiredError(
        "No valid Silpo MCP token on disk — callback_handler was reached, "
        "meaning the redirect handler should already have failed first."
    )
