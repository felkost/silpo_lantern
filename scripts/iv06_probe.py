"""IV-06 (plan section 8.3, G7 stage plan section 5): does Render's own
network egress reach `https://mcp.silpo.ua/mcp` at all? Cloudflare has
blocked at least one US-cloud egress before (plan section 17's risk
table), so this is checked BEFORE any deploy, not assumed.

One JSON-RPC call — `initialize` -- is enough to answer the question: a
valid JSON-RPC response means Render's egress reaches the server; a 403
or a timeout means it does not, and the plan's own rule applies without
regret: Render is struck out, the demo stays local (D-G7-09 already
chose not to need Dockerfiles for this). Deliberately NOT `tools/list`:
that call needs a completed OAuth exchange this probe has no reason to
perform, and the egress question is answered by the TCP/TLS handshake
and the server's own JSON-RPC framing alone, authenticated or not.

Two modes:

  (no flags)   Runs the probe once, prints PASS/FAIL, exits 0/1. What
               the author runs locally first, to see the script itself
               work before trusting Render's own network.

  --serve      Starts a minimal HTTP server on $PORT (Render's own
               convention) that re-runs the SAME probe on every request
               to `/` and returns the result as JSON -- so `render.yaml`
               can point a browser or curl at the deployed service and
               get a live answer, not a cached one from build time.
               Render's health check hitting `/` is itself part of the
               evidence: a healthy deploy already proves the egress.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_MCP_URL = "https://mcp.silpo.ua/mcp"
OUT_DIR = Path(__file__).resolve().parent.parent / "datasets" / "evidence"


async def _probe_once(mcp_url: str, timeout_seconds: float) -> Dict[str, Any]:
    """Deliberately unauthenticated -- no `DiskTokenStorage`, no OAuth
    provider. Measured directly against the live server: an unauthenticated
    `initialize` gets HTTP 401 from `mcp.silpo.ua` itself, at the HTTP
    layer, before any JSON-RPC content is even parsed. That is exactly
    the evidence IV-06 needs -- 401 proves the TCP/TLS handshake AND the
    HTTP round trip both reached the real server; only a genuine
    egress block (Cloudflare 403, or a timeout/DNS/connection failure)
    means Render's network cannot reach it. PASS is therefore "the
    server answered at all", not "the request was authorized".
    """
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    import httpx

    started = time.monotonic()
    try:
        async with asyncio.timeout(timeout_seconds):
            async with streamablehttp_client(mcp_url) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    result = await session.initialize()
                    elapsed = time.monotonic() - started
                    return {
                        "pass": True,
                        "elapsed_seconds": round(elapsed, 2),
                        "reason": "valid JSON-RPC response (unexpectedly authorized)",
                        "server_info": {
                            "name": result.serverInfo.name,
                            "version": result.serverInfo.version,
                        },
                    }
    except Exception as exc:  # noqa: BLE001 -- IV-06's job is "did anything go wrong"
        # `anyio`'s own task groups (streamable-HTTP transport, then the
        # session's own group) wrap the real cause in one or more layers
        # of `ExceptionGroup` -- same unwrap as `scripts/g4_live_evidence_gate_run.py`
        # and `scripts/record_replay_bundle.py`.
        cause: BaseException = exc
        while isinstance(cause, BaseExceptionGroup) and len(cause.exceptions) == 1:
            cause = cause.exceptions[0]
        elapsed = time.monotonic() - started

        status_code = (
            cause.response.status_code
            if isinstance(cause, httpx.HTTPStatusError)
            else None
        )
        # Plan section 8.3's own criterion: 403 (Cloudflare's block page)
        # or a timeout/connection failure means the egress is blocked.
        # Any OTHER HTTP status (401 included) means a real server
        # answered a real HTTP request -- the network path works.
        network_reached = status_code is not None and status_code != 403
        return {
            "pass": network_reached,
            "elapsed_seconds": round(elapsed, 2),
            "reason": (
                f"server answered HTTP {status_code} -- egress confirmed"
                if network_reached
                else "no HTTP response from the server (blocked or unreachable)"
            ),
            "error_type": type(cause).__name__,
            "error": str(cause),
            "http_status": status_code,
        }


def run_probe_once(
    mcp_url: str = DEFAULT_MCP_URL, timeout_seconds: float = 15.0
) -> Dict[str, Any]:
    result = asyncio.run(_probe_once(mcp_url, timeout_seconds))
    result["mcp_url"] = mcp_url
    result["probed_at"] = datetime.now(timezone.utc).isoformat()
    result["render_region"] = os.environ.get("RENDER_REGION", "not-on-render")
    return result


class _ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's own naming
        result = run_probe_once()
        body = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200 if result["pass"] else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        print(f"[iv06_probe] {self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    args = parser.parse_args()

    if args.serve:
        port = int(os.environ.get("PORT", "8000"))
        server = ThreadingHTTPServer(("0.0.0.0", port), _ProbeHandler)
        print(f"IV-06 probe serving on 0.0.0.0:{port} -- GET / to re-run the probe")
        server.serve_forever()
        return

    result = run_probe_once(args.mcp_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"iv06_probe_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"evidence written to {out_path} (gitignored)")

    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
