"""Per-guest `TokenStorage`: the guest's own OAuth token comes from Neon,
keyed by their recovery session; the OAuth CLIENT registration comes from
one app-level file shared by every guest.

Those two halves have genuinely different lifetimes, which is why they
live in different places: a client registration identifies the
APPLICATION to Silpo's authorization server (registered once, by
`scripts/g5_register_oauth_client.py`), while a token identifies ONE
GUEST (issued every time somebody completes a phone+OTP login). The
single-file `DiskTokenStorage` conflates them, which is exactly why it
cannot serve more than one guest: a second person authorising overwrites
the first, and both then read the same cart.

Implements `mcp.client.auth.oauth2.TokenStorage` structurally (it is a
`Protocol`, not an ABC), the same way `DiskTokenStorage` does.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from psycopg_pool import ConnectionPool

from src.lantern.mcp.auth import WEB_CLIENT_PATH
from src.lantern.memory.repository import load_session_token, save_session_token


class SessionTokenStorage:
    def __init__(
        self,
        pool: ConnectionPool,
        session_id: str,
        client_info_path: Path = WEB_CLIENT_PATH,
    ) -> None:
        self._pool = pool
        self._session_id = session_id
        self._client_info_path = client_info_path

    async def get_tokens(self) -> Optional[OAuthToken]:
        raw = load_session_token(self._pool, self._session_id)
        if raw is None:
            return None
        return OAuthToken.model_validate(raw)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        save_session_token(
            self._pool,
            self._session_id,
            tokens.model_dump(mode="json", exclude_none=True),
        )

    async def get_client_info(self) -> Optional[OAuthClientInformationFull]:
        """App-level, not per-session: every guest authorises against the
        same registered client, and only the token that comes back differs.
        """
        if not self._client_info_path.exists():
            return None
        raw: Dict[str, Any] = json.loads(
            self._client_info_path.read_text(encoding="utf-8")
        )
        return OAuthClientInformationFull.model_validate(raw)

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info_path.parent.mkdir(parents=True, exist_ok=True)
        self._client_info_path.write_text(
            client_info.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )
