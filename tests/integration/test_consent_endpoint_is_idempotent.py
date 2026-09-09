"""T15 (G8 stage spec, D-G8-07): a double-clicked consent (or a retried
request) must not 500 -- `repository.save_consent` used to be a bare
`INSERT` against `action_id UUID PRIMARY KEY`, so a second call for the
same action_id raised a unique-violation. Integration, not unit: "exactly
one row" is only assertable against a real Postgres, and every existing
test of `repository.py`'s raw SQL lives here for that reason
(`test_repository_roundtrips.py`'s own docstring).
"""

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from psycopg_pool import ConnectionPool

from src.lantern.config import strip_sqlalchemy_dialect
from src.lantern.domain.models import ConsentRecord
from src.lantern.memory.migrations_runner import run_migrations
from src.lantern.memory.repository import (
    create_session,
    open_repository_pool,
    save_consent,
)

OWNER = "owner-hash-for-idempotency-test"

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


@contextmanager
def _temporary_session(dsn: str, session_id: str) -> Iterator[ConnectionPool]:
    with open_repository_pool(dsn) as pool:
        create_session(pool, session_id, session_id, OWNER)
        try:
            yield pool
        finally:
            with pool.connection() as conn:
                conn.execute(
                    "DELETE FROM consents WHERE session_id = %s", (session_id,)
                )
                conn.execute(
                    "DELETE FROM sessions WHERE session_id = %s", (session_id,)
                )


def _consent(session_id: str, action_id: str) -> ConsentRecord:
    now = datetime.now(timezone.utc)
    return ConsentRecord(
        action_id=action_id,
        session_id=session_id,
        owner=OWNER,
        cart_id="cart-1",
        canonical_args={
            "shoppingCartId": "cart-1",
            "products": [{"productId": "p-1", "quantity": 2, "addQuantity": False}],
        },
        args_hash="a" * 64,
        state_hash="b" * 64,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )


async def test_saving_the_same_consent_twice_leaves_exactly_one_row() -> None:
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    await run_migrations(dsn)
    session_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())

    with _temporary_session(dsn, session_id) as pool:
        consent = _consent(session_id, action_id)
        save_consent(pool, consent)  # first click
        save_consent(pool, consent)  # a double click -- must not raise

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM consents WHERE action_id = %s", (action_id,)
                )
                row = cur.fetchone()
        assert row is not None
        assert row[0] == 1
