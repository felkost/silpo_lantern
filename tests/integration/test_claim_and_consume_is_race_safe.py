"""T11 (G5+G6 stage spec): three sequential **and three parallel**
duplicate claims resolve to exactly one write.

The sequential half was already covered. The parallel half is the reason
this file exists, and it is the property the whole write path rests on:
`claim_and_consume` decides who may write by racing an
`INSERT ... ON CONFLICT DO NOTHING ... RETURNING` against the idempotency
journal, and until now that behaviour was reasoned about from the SQL and
never actually raced. A guest double-clicking, or a client retrying a
request, is exactly two simultaneous claims.

Real threads against a real pool, because the thing under test is what
Postgres does when two transactions insert the same key at the same time.
A fake pool would answer with whatever the test author decided, which is
the failure mode `test_repository_roundtrips.py` was written after.
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, List, Tuple

import pytest
from psycopg_pool import ConnectionPool

from src.lantern.config import strip_sqlalchemy_dialect
from src.lantern.domain.models import ConsentRecord
from src.lantern.memory.migrations_runner import run_migrations
from src.lantern.memory.repository import (
    IdempotencyState,
    claim_and_consume,
    create_session,
    open_repository_pool,
    save_consent,
)

OWNER = "owner-hash-for-race-test"
CART_ID = "cart-for-race-test"

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


def _dsn() -> str:
    return strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])


@contextmanager
def _consent_ready(session_id: str, action_id: str) -> Iterator[ConnectionPool]:
    """Creates one session and one unconsumed consent, and removes both
    plus the journal row afterwards. These tests share the Neon database
    G8+G9 reads its metrics from, so a leftover synthetic claim is a wrong
    number later, not clutter."""
    dsn = _dsn()
    with open_repository_pool(dsn) as pool:
        create_session(pool, session_id, session_id, OWNER)
        now = datetime.now(timezone.utc)
        save_consent(
            pool,
            ConsentRecord(
                action_id=action_id,
                session_id=session_id,
                owner=OWNER,
                cart_id=CART_ID,
                canonical_args={"shoppingCartId": CART_ID, "products": []},
                args_hash="args-hash-for-race-test",
                state_hash="state-hash-for-race-test",
                created_at=now,
                expires_at=now + timedelta(minutes=5),
            ),
        )
        try:
            yield pool
        finally:
            with pool.connection() as conn:
                conn.execute(
                    "DELETE FROM idempotency_keys WHERE action_id = %s", (action_id,)
                )
                conn.execute("DELETE FROM consents WHERE action_id = %s", (action_id,))
                conn.execute(
                    "DELETE FROM sessions WHERE session_id = %s", (session_id,)
                )


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    import asyncio

    asyncio.run(run_migrations(_dsn()))


def _claim(pool: ConnectionPool, action_id: str) -> Tuple[bool, IdempotencyState]:
    return claim_and_consume(pool, OWNER, CART_ID, action_id, "args-hash-for-race-test")


def test_t11_three_sequential_claims_yield_exactly_one_winner() -> None:
    session_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())

    with _consent_ready(session_id, action_id) as pool:
        results = [_claim(pool, action_id) for _ in range(3)]

    winners = [claimed for claimed, _ in results if claimed]
    assert len(winners) == 1, f"expected one winner, got {results}"
    # The losers must be distinguishable from the winner by the flag alone,
    # not by the state string: both see `in_flight` (D27).
    assert all(state == "in_flight" for _, state in results)


def test_t11_three_parallel_claims_yield_exactly_one_winner() -> None:
    """The case that was never tested. Three threads enter
    `claim_and_consume` at the same moment against the same journal key;
    Postgres must let exactly one of them through.
    """
    session_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())

    with _consent_ready(session_id, action_id) as pool:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(_claim, pool, action_id) for _ in range(3)]
            results: List[Tuple[bool, IdempotencyState]] = [
                future.result(timeout=30) for future in futures
            ]

    winners = [claimed for claimed, _ in results if claimed]
    assert len(winners) == 1, (
        "exactly one caller may be told it claimed the action — anything else "
        f"means a duplicate write is possible: {results}"
    )


def test_t11_the_consent_is_consumed_exactly_once_under_a_race() -> None:
    """The claim and the consent's consumption are one transaction
    (D-G5-07b). If three threads race and two of them still managed to
    stamp `consumed_at`, the journal would be right and the consent record
    would be lying about who spent it.
    """
    session_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())

    with _consent_ready(session_id, action_id) as pool:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(_claim, pool, action_id) for _ in range(3)]
            for future in futures:
                future.result(timeout=30)

        with pool.connection() as conn:
            row = conn.execute(
                "SELECT consumed_at FROM consents WHERE action_id = %s", (action_id,)
            ).fetchone()
            journal = conn.execute(
                "SELECT count(*) FROM idempotency_keys WHERE action_id = %s",
                (action_id,),
            ).fetchone()

    assert row is not None and row[0] is not None, "the consent was never consumed"
    assert journal is not None and journal[0] == 1, "more than one journal row exists"


def test_t11_a_second_action_on_the_same_cart_is_independent() -> None:
    """A guard against over-tightening: the uniqueness is per action, not
    per cart. Two different approved actions on one cart must both be
    claimable, or a second consent round (D42) could never write."""
    session_id = str(uuid.uuid4())
    first, second = str(uuid.uuid4()), str(uuid.uuid4())

    with _consent_ready(session_id, first) as pool:
        with _consent_ready(str(uuid.uuid4()), second) as _:
            claimed_first, _state = _claim(pool, first)
            claimed_second, _state2 = _claim(pool, second)

    assert claimed_first is True
    assert claimed_second is True
