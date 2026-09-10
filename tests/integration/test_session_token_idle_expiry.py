"""G10 delivery A (T5, A-G10-04): a token row idle longer than
`SESSION_IDLE_TTL` is refused AND deleted on the next read; a live one is
touched, so "idle" means since the last use, not since login. Evaluated
against Postgres's own `now()` (D-G5-09), which is why this cannot be a
unit test.
"""

import os
import uuid
from contextlib import contextmanager
from typing import Iterator

import pytest
from psycopg_pool import ConnectionPool

from src.lantern.config import strip_sqlalchemy_dialect
from src.lantern.memory.migrations_runner import run_migrations
from src.lantern.memory.repository import (
    SESSION_IDLE_TTL,
    create_session,
    load_session_token,
    open_repository_pool,
    save_session_token,
)

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


@contextmanager
def _session(dsn: str, session_id: str) -> Iterator[ConnectionPool]:
    with open_repository_pool(dsn) as pool:
        create_session(pool, session_id, session_id, "owner-idle-expiry-test")
        try:
            yield pool
        finally:
            with pool.connection() as conn:
                conn.execute(
                    "DELETE FROM sessions WHERE session_id = %s", (session_id,)
                )


def _row_count(pool: ConnectionPool, session_id: str) -> int:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT count(*) FROM oauth_tokens WHERE session_id = %s", (session_id,)
        ).fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.asyncio
async def test_an_idle_token_is_refused_and_deleted() -> None:
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    await run_migrations(dsn)
    session_id = str(uuid.uuid4())
    with _session(dsn, session_id) as pool:
        save_session_token(pool, session_id, {"access_token": "t"})
        with pool.connection() as conn:
            conn.execute(
                "UPDATE oauth_tokens SET updated_at = now() - %s - interval '1 second'"
                " WHERE session_id = %s",
                (SESSION_IDLE_TTL, session_id),
            )

        assert load_session_token(pool, session_id) is None
        assert _row_count(pool, session_id) == 0


@pytest.mark.asyncio
async def test_a_live_token_is_returned_and_touched() -> None:
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    await run_migrations(dsn)
    session_id = str(uuid.uuid4())
    with _session(dsn, session_id) as pool:
        save_session_token(pool, session_id, {"access_token": "t"})
        with pool.connection() as conn:
            conn.execute(
                "UPDATE oauth_tokens SET updated_at = now() - interval '10 minutes'"
                " WHERE session_id = %s",
                (session_id,),
            )

        assert load_session_token(pool, session_id) == {"access_token": "t"}
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT now() - updated_at < interval '1 minute' FROM oauth_tokens"
                " WHERE session_id = %s",
                (session_id,),
            ).fetchone()
        assert row is not None and row[0] is True
