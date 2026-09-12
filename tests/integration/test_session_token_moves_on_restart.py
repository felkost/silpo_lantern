"""«Перевірити знову» moves the credential to the new session in one
transaction: the old session keeps its rows and loses its token, the new
one can read the cart. Against a real Postgres because the move is a
DELETE ... RETURNING feeding an INSERT inside one transaction.
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
    create_session,
    load_session_token,
    move_session_token,
    open_repository_pool,
    save_session_token,
)

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


@contextmanager
def _sessions(dsn: str, ids: list[str]) -> Iterator[ConnectionPool]:
    with open_repository_pool(dsn) as pool:
        for sid in ids:
            create_session(pool, sid, sid, "owner-restart-test")
        try:
            yield pool
        finally:
            with pool.connection() as conn:
                for sid in ids:
                    conn.execute(
                        "DELETE FROM oauth_tokens WHERE session_id = %s", (sid,)
                    )
                    conn.execute("DELETE FROM sessions WHERE session_id = %s", (sid,))


@pytest.mark.asyncio
async def test_the_token_moves_and_the_old_session_is_logged_out() -> None:
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    await run_migrations(dsn)
    old, new = str(uuid.uuid4()), str(uuid.uuid4())
    with _sessions(dsn, [old, new]) as pool:
        save_session_token(pool, old, {"access_token": "t"})

        assert move_session_token(pool, old, new) is True

        assert load_session_token(pool, old) is None
        assert load_session_token(pool, new) == {"access_token": "t"}
        # a second restart from the now-empty old session finds nothing
        assert move_session_token(pool, old, str(uuid.uuid4())) is False
