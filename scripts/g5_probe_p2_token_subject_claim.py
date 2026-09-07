"""Probe P2 (G5+G6 stage spec): does the cached OAuth token carry a stable
subject claim usable as `owner`'s primary source (D-G5-06)? Local file read
only, no network call, free.

Usage:
    .venv/Scripts/python.exe scripts/g5_probe_p2_token_subject_claim.py
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.mcp.auth import DEFAULT_TOKEN_PATH  # noqa: E402


def _decode_jwt_payload(token: str) -> dict | None:
    """Decodes a JWT's payload segment without verifying the signature —
    this probe only asks "is there a `sub` claim", not "is the token
    valid"; verification is the OAuth library's job elsewhere."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None


def main() -> None:
    if not DEFAULT_TOKEN_PATH.exists():
        print(
            f"No cached token at {DEFAULT_TOKEN_PATH} — run "
            "scripts/silpo_mcp_login.py first."
        )
        sys.exit(1)

    data = json.loads(DEFAULT_TOKEN_PATH.read_text(encoding="utf-8"))
    access_token = data.get("access_token", "")
    print(f"Token keys present: {sorted(data.keys())}")

    payload = _decode_jwt_payload(access_token)
    if payload is None:
        print(
            "access_token is not a 3-part JWT (or its payload segment "
            "doesn't decode as JSON) — no `sub` claim available this way."
        )
        print(
            "D-G5-06 fallback applies: owner derives from the sessions "
            "row + a server-side secret, never from cart_id."
        )
        return

    print("Decoded JWT payload keys:", sorted(payload.keys()))
    sub = payload.get("sub")
    if sub:
        print(f"Stable subject claim found: sub={sub!r}")
        print(
            "D-G5-06 primary branch applies: "
            'owner = sha256("lantern-owner-v1|" + sub)'
        )
    else:
        print("No `sub` claim in the payload.")
        print(
            "D-G5-06 fallback applies: owner derives from the sessions "
            "row + a server-side secret, never from cart_id."
        )


if __name__ == "__main__":
    main()
