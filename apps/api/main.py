"""FastAPI app entrypoint. `GET /health` is liveness only — no I/O — so it
stays a free, offline contract test (confirmed: a bare
`TestClient(app).get(...)`, without `with`, never runs `lifespan` in this
FastAPI/Starlette version — the health check's own network-free guarantee
does not depend on the lifespan below being absent).

G5+G6: `app.state.graph_builder` builds and caches the production graph
LAZILY, on first use inside a route handler -- never inside this lifespan.
Building it eagerly here would require a live `OPENROUTER_API_KEY` and a
live `tools/list` MCP call just to *start* the app, breaking `/health`'s
own network-free guarantee and `tests/integration/test_app_starts.py`
(which needs only `DATABASE_URL`). The offline route tests substitute a
fake builder via `app.state.graph_builder = ...` before any request.
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI

from apps.api.oauth_routes import router as oauth_router
from apps.api.routes import router
from src.lantern.config import (
    get_database_url,
    get_owner_secret,
    strip_sqlalchemy_dialect,
)
from src.lantern.graph.state import recovery_state_serde
from src.lantern.memory.checkpointer import get_checkpointer
from src.lantern.memory.migrations_runner import run_migrations
from src.lantern.memory.repository import open_repository_pool
from src.lantern.observability.tracer import install_trace_redaction

# Windows-only: asyncio's default ProactorEventLoop cannot run psycopg's
# async mode at all (measured — see tests/conftest.py for the identical
# fix on the test side). Must run before any async psycopg connection is
# ever opened, i.e. before uvicorn starts serving.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Before anything can emit a span: LangSmith's client is built once, on
    # first use, and later arguments are ignored.
    install_trace_redaction()
    dsn = strip_sqlalchemy_dialect(get_database_url())
    await run_migrations(dsn)
    # D-G5-15: `recovery_state_serde()` extends the msgpack allowlist with
    # `ConsentRecord`/`Receipt`/`CartDiff` -- without it, a consent
    # crossing the `interrupt_before` checkpoint boundary degrades exactly
    # as `ActionProposal` once did before it was added to the same list.
    async with get_checkpointer(dsn, serde=recovery_state_serde()) as saver:
        app.state.checkpointer = saver
        with open_repository_pool(dsn) as pool:
            app.state.repo_pool = pool
            app.state.owner_secret = get_owner_secret()
            app.state.version_tuple = {}
            app.state.graph = None
            # `oauth_routes.py`: state -> PKCE verifier, single-worker
            # in-process store (same assumption `ToolRegistry` already
            # documents for this project).
            app.state.oauth_pending = {}

            def build_graph() -> Any:
                if app.state.graph is None:
                    from src.lantern.graph.production import build_production_graph

                    graph, version_tuple = build_production_graph(pool, saver)
                    app.state.graph = graph
                    app.state.version_tuple = version_tuple
                return app.state.graph

            app.state.graph_builder = build_graph
            yield


app = FastAPI(title="Lantern API", lifespan=lifespan)
app.include_router(router)
app.include_router(oauth_router)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}
