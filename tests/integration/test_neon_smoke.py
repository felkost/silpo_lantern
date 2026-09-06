"""D-G1-04: integration tests need a real Neon
Postgres and are never part of `make gate`/CI (no reachable Postgres there).
Skips cleanly when `DATABASE_URL` is unset (F5) rather than failing with a
confusing connection-refused error.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set — see D-G1-04"
)


@pytest.mark.asyncio
async def test_neon_connection_is_reachable() -> None:
    import psycopg

    from src.lantern.config import strip_sqlalchemy_dialect

    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT version()")
            (version,) = await cur.fetchone()
            assert "PostgreSQL" in version
