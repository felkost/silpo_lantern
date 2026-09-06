"""FastAPI app entrypoint (D-G1-03, docs/g1-g2-stage-spec.md). `GET /health`
is liveness only — no I/O — so it stays a free, offline contract test
(confirmed: a bare `TestClient(app).get(...)`, without `with`, never runs
`lifespan` in this FastAPI/Starlette version — the health check's own
network-free guarantee does not depend on the lifespan below being absent).

The MCP client is deliberately **not** wired into this lifespan yet: no
route exists this stage that consumes a live MCP session, and the OAuth
token doesn't exist until a human completes the one-time phone+OTP login
(R1, docs/g1-g2-stage-spec.md) — starting the app would otherwise fail
before it could even serve `/health`. It becomes lifespan-managed once G3+
adds the first route that needs it.
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

from fastapi import FastAPI

from src.lantern.config import get_database_url, strip_sqlalchemy_dialect
from src.lantern.memory.checkpointer import get_checkpointer
from src.lantern.memory.migrations_runner import run_migrations

# Windows-only: asyncio's default ProactorEventLoop cannot run psycopg's
# async mode at all (measured — see tests/conftest.py for the identical
# fix on the test side). Must run before any async psycopg connection is
# ever opened, i.e. before uvicorn starts serving.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    dsn = strip_sqlalchemy_dialect(get_database_url())
    await run_migrations(dsn)
    async with get_checkpointer(dsn) as saver:
        app.state.checkpointer = saver
        yield


app = FastAPI(title="Lantern API", lifespan=lifespan)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}
