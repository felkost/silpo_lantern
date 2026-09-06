"""F10 (docs/g1-g2-stage-spec.md): a previously-valid `DiskTokenStorage`
token being rejected mid-session must surface as a distinct error from a
fresh "never logged in" — otherwise a mid-demo expiry looks identical to a
step nobody ever completed. The distinguishing fact is measurable and cheap:
whether a token was ever written to disk, not an invented behavioural
difference in the OAuth flow itself.
"""

import asyncio
from pathlib import Path

import pytest

from src.lantern.mcp.auth import (
    DiskTokenStorage,
    SilpoMcpAuthRequiredError,
    build_redirect_handler,
)
from src.lantern.mcp.errors import McpAuthExpiredError


def test_raises_auth_required_when_no_token_was_ever_stored(tmp_path: Path) -> None:
    storage = DiskTokenStorage(path=tmp_path / "token.json")
    handler = build_redirect_handler(storage)

    with pytest.raises(SilpoMcpAuthRequiredError):
        asyncio.run(handler("https://example.invalid/authorize"))


def test_raises_auth_expired_when_a_token_previously_existed(tmp_path: Path) -> None:
    from mcp.shared.auth import OAuthToken

    storage = DiskTokenStorage(path=tmp_path / "token.json")
    asyncio.run(
        storage.set_tokens(OAuthToken(access_token="stale", token_type="Bearer"))
    )
    handler = build_redirect_handler(storage)

    with pytest.raises(McpAuthExpiredError):
        asyncio.run(handler("https://example.invalid/authorize"))
