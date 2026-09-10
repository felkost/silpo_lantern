"""Process entry point: `python -m apps.api` (what `make run` invokes).

Windows needs this launcher rather than a plain `uvicorn apps.api.main:app`.
Measured at G1+G2 stage close, against the installed uvicorn 0.52:

- `uvicorn.Server.run()` calls `asyncio_run(...)` with the loop factory from
  `config.get_loop_factory()`, and `uvicorn/loops/asyncio.py` returns
  `asyncio.ProactorEventLoop` on win32.
- A `loop_factory` ignores `asyncio.set_event_loop_policy` entirely, so setting
  the selector policy — in this file or in `main.py` — has no effect on the
  loop uvicorn actually runs.
- psycopg's async mode refuses a `ProactorEventLoop`, so the lifespan crashed
  on its first database call.

The fix drives `Server.serve()` inside our own `asyncio.run(...)` with an
explicit selector loop factory. `reload` stays off: the reloader runs the app
in a child process that would not inherit this loop.
"""

import asyncio
import os
import sys
from typing import Any, Dict

import uvicorn


def main() -> None:
    # G7 (IV-07): Render injects its own $PORT and expects a bind on
    # 0.0.0.0 -- `LANTERN_API_PORT`/`LANTERN_API_HOST` stay the local-dev
    # defaults (127.0.0.1:8000) so nothing about a plain `make run`
    # changes; $PORT wins only when Render (or any host following the
    # same convention) actually sets it.
    on_render = "PORT" in os.environ
    # G10 (D89): behind Render's proxy `request.client.host` is the proxy
    # unless X-Forwarded-For is trusted -- and the per-IP session cap would
    # then be one shared cap for everyone. Local dev keeps uvicorn's default.
    proxy: Dict[str, Any] = {"forwarded_allow_ips": "*"} if on_render else {}
    config = uvicorn.Config(
        "apps.api.main:app",
        host=os.environ.get(
            "LANTERN_API_HOST", "0.0.0.0" if on_render else "127.0.0.1"
        ),
        port=int(os.environ.get("PORT") or os.environ.get("LANTERN_API_PORT", "8000")),
        reload=False,
        **proxy,
    )
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        server.run()


if __name__ == "__main__":
    main()
