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
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from src.lantern.config import PROJECT_ROOT
from src.lantern.mcp.errors import McpAuthExpiredError

DEFAULT_TOKEN_PATH = PROJECT_ROOT / ".cache" / "silpo_mcp_token.json"


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
    storage: DiskTokenStorage,
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
