"""The checkpointer is built over an `AsyncConnectionPool`, not a single
held connection, precisely because a single connection has no way to
survive Neon's own idle-suspend behavior or a transient network blip.
Simulates a dropped connection underneath the pool and confirms the next
checkpoint-level operation still succeeds — the pool itself handles
reconnection, nothing in application code has to.
"""

import os

import pytest

from src.lantern.config import strip_sqlalchemy_dialect
from src.lantern.memory.checkpointer import get_checkpointer

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


@pytest.mark.asyncio
async def test_pool_recovers_after_a_connection_is_dropped_underneath_it() -> None:
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])

    async with get_checkpointer(dsn) as saver:
        pool = saver.conn

        # Simulate the connection dying underneath the pool (Neon idle-suspend,
        # a transient network blip): check one out, close its socket directly,
        # hand it back — the pool must detect and discard it, not hand a dead
        # connection to the next caller.
        conn = await pool.getconn()
        await conn.close()
        await pool.putconn(conn)

        results = [
            item
            async for item in saver.alist(
                {"configurable": {"thread_id": "does-not-exist"}}
            )
        ]
        assert results == []
