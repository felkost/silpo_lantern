"""Live, local-only capture of one MCP tool call's raw response, for
`scripts/sanitize_fixture.py` to turn into a committable fixture. Never run
in CI — needs a completed one-time phone+OTP login (`DiskTokenStorage`)
before it can do anything at all.

Uses the raw `mcp` SDK directly (`ClientSession` + `streamablehttp_client`),
matching this project's own MCP client (`src/lantern/mcp/client.py`) — not
the donor's `langchain_mcp_adapters` wrapper, which this project does not
depend on (confirmed: `langchain-mcp-adapters` is not in requirements.txt;
that wrapper exists to turn MCP tools into LangChain tools for an
LLM-tool-calling loop this project does not need).

Not yet run live — the first run is the human OAuth step this script exists
to require. Signatures below are measured against the installed
`mcp==1.29.0` SDK; the end-to-end flow itself is unverified until that first
run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.mcp.auth import (  # noqa: E402
    DiskTokenStorage,
    build_redirect_handler,
    callback_handler,
)

DEFAULT_MCP_URL = "https://mcp.silpo.ua/mcp"
RAW_OUTPUT_DIR = Path("datasets") / "fixtures" / "raw"  # gitignored


async def _capture(
    tool_name: str, arguments: Dict[str, Any], mcp_url: str
) -> Dict[str, Any]:
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
        redirect_handler=build_redirect_handler(storage),
        callback_handler=callback_handler,
    )
    async with streamablehttp_client(mcp_url, auth=auth) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result.model_dump(mode="json")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture one live MCP tool call's raw response (local-only, never CI)."
        )
    )
    parser.add_argument("tool_name")
    parser.add_argument("--args", default="{}", help="JSON-encoded tool arguments")
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    parser.add_argument("--out-dir", type=Path, default=RAW_OUTPUT_DIR)
    args = parser.parse_args(argv)

    arguments = json.loads(args.args)
    raw = asyncio.run(_capture(args.tool_name, arguments, args.mcp_url))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.fixture_id}.json"
    out_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path} (raw — never commit this; sanitize it first)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
