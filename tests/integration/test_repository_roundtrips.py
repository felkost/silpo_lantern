"""The repository's read paths against a real Postgres, which is the only
place they can be tested: their whole job is turning driver-typed rows back
into domain objects, and a fake pool returns whatever the test author typed
rather than what psycopg actually produces.

Written after a live run failed here. `consents.action_id` and
`consents.session_id` are UUID columns, so psycopg hands them back as
`uuid.UUID` while `ConsentRecord` declares both `str` -- `load_consent`
raised `ValidationError` inside the Write Guard node, on the first real
consent this project ever recorded. Every existing test of that path used a
`load_consent` double, so nothing offline could have caught it.
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
    get_session,
    load_consent,
    open_repository_pool,
    save_consent,
)

OWNER = "owner-hash-for-roundtrip-test"

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


@contextmanager
def _temporary_session(dsn: str, session_id: str) -> Iterator[ConnectionPool]:
    """Deletes everything this test wrote before it returns. These tests run
    against the same Neon database the metrics stage reads its metrics from, so a
    leftover synthetic consent is not untidiness -- it is a wrong number in
    `ConsentRate`/`ReadbackCoverage` later.
    """
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
        prompt_version="planner_v1",
        policy_version="d6bb30e47b48",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        consumed_at=None,
    )


async def test_consent_roundtrips_with_string_ids() -> None:
    """A consent read back must be usable by the Write Guard, whose
    comparisons (`consent.session_id == state.session_id`) are string
    equality -- a `uuid.UUID` there fails validation before it can even be
    compared."""
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    await run_migrations(dsn)

    session_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())

    with _temporary_session(dsn, session_id) as pool:
        save_consent(pool, _consent(session_id, action_id))
        record, expired = load_consent(pool, action_id)

    assert record is not None
    assert not expired
    assert record.action_id == action_id
    assert record.session_id == session_id
    assert isinstance(record.action_id, str)
    assert isinstance(record.session_id, str)
    assert record.canonical_args["shoppingCartId"] == "cart-1"


async def test_get_session_returns_string_ids() -> None:
    """`get_session` declares `Dict[str, str]`; `sessions.session_id` is a
    UUID column, so without conversion that annotation is false and the
    next caller to read the key gets a `uuid.UUID`."""
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    await run_migrations(dsn)

    session_id = str(uuid.uuid4())

    with _temporary_session(dsn, session_id) as pool:
        row = get_session(pool, session_id)

    assert row is not None
    assert row["session_id"] == session_id
    assert isinstance(row["session_id"], str)
    assert row["owner"] == OWNER


async def test_expired_consent_is_reported_expired() -> None:
    """The expiry flag is evaluated database-side, so it can only
    be tested against a real `now()`."""
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    await run_migrations(dsn)

    session_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())
    consent = _consent(session_id, action_id)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired_consent = consent.model_copy(update={"expires_at": past})

    with _temporary_session(dsn, session_id) as pool:
        save_consent(pool, expired_consent)
        record, expired = load_consent(pool, action_id)

    assert record is not None
    assert expired
