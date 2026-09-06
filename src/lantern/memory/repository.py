"""The Write Guard's own persistence: consents, the idempotency journal,
and receipts. Sync (`psycopg_pool.ConnectionPool`), deliberately separate
from `checkpointer.py`'s async pool -- the checkpointer serializes
`RecoveryState` across the LangGraph interrupt boundary, this module
authorizes and records one write. Both point at the same Neon database;
neither needs to know the other's connection.

D-G5-15: kept sync on purpose. `apps/api` resumes the graph with
`await graph.ainvoke(...)`, but node bodies stay ordinary sync functions --
a sync `ConnectionPool` call inside a sync node runs in FastAPI's default
threadpool executor, never on the event loop thread the async checkpointer
owns. This is the only reason the Windows `ProactorEventLoop` constraint
on psycopg's own async mode does not apply here: sync psycopg is
loop-independent regardless of which event loop policy is active.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator, Literal, Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.lantern.domain.models import ConsentRecord, Receipt

# The five states `0004_idempotency_keys.sql`'s own CHECK constraint
# declares -- kept as a literal here (mypy needs the members statically),
# with a test (`test_idempotency_states_match_migration_check.py`) that
# parses the SQL and asserts this list is not out of sync with it, rather
# than trusting a second hand-typed copy to stay correct on its own.
IdempotencyState = Literal["prepared", "in_flight", "confirmed", "failed", "unknown"]

MAX_POOL_SIZE = 5


class ActionAlreadyInFlightError(Exception):
    """Raised by `claim_and_consume` when the journal row for this
    `(owner, cart_id, action_id)` already exists with a different
    `canonical_args_hash` -- the same logical action requested with
    different arguments, which plan section 11.1 requires be rejected
    rather than silently overwritten."""


class ConsentAlreadyConsumedError(Exception):
    """Raised by `claim_and_consume` when the consent row has no
    unconsumed row to claim -- either it was already used, or it does not
    exist for this `action_id`."""


@contextmanager
def open_repository_pool(dsn: str) -> Iterator[ConnectionPool]:
    """Opens a small sync pool for the lifetime of the `with` block.
    `apps/api`'s own lifespan owns one instance for the process; tests use
    a short-lived one per test via this same entry point."""
    pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=MAX_POOL_SIZE, open=True)
    try:
        yield pool
    finally:
        pool.close()


def create_session(
    pool: ConnectionPool, session_id: str, thread_id: str, owner: str
) -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, thread_id, owner) VALUES (%s, %s, %s)",
            (session_id, thread_id, owner),
        )


def save_consent(pool: ConnectionPool, consent: ConsentRecord) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO consents
                (action_id, session_id, owner, cart_id, canonical_args, args_hash,
                 state_hash, prompt_version, policy_version, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                consent.action_id,
                consent.session_id,
                consent.owner,
                consent.cart_id,
                json.dumps(consent.canonical_args),
                consent.args_hash,
                consent.state_hash,
                consent.prompt_version,
                consent.policy_version,
                consent.expires_at,
            ),
        )


def load_consent(
    pool: ConnectionPool, action_id: str
) -> tuple[Optional[ConsentRecord], bool]:
    """Returns `(record, expired)`. `expired` is evaluated **database-side**
    (`expires_at <= now()`) rather than against a Python clock passed in --
    D-G5-09: the row is stamped by Postgres's own `now()`, and a few
    minutes of container clock skew must not be able to kill a valid
    consent or resurrect a dead one."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *, (expires_at <= now()) AS expired
                FROM consents WHERE action_id = %s
                """,
                (action_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None, True
    expired = row.pop("expired")
    record = ConsentRecord(
        action_id=row["action_id"],
        session_id=row["session_id"],
        owner=row["owner"],
        cart_id=row["cart_id"],
        canonical_args=row["canonical_args"],
        args_hash=row["args_hash"],
        state_hash=row["state_hash"],
        prompt_version=row["prompt_version"],
        policy_version=row["policy_version"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        consumed_at=row["consumed_at"],
    )
    return record, bool(expired)


def claim_and_consume(
    pool: ConnectionPool,
    owner: str,
    cart_id: str,
    action_id: str,
    canonical_args_hash: str,
) -> IdempotencyState:
    """D-G5-07b: the idempotency claim and the consent consumption happen
    in one transaction, immediately before the write call, inside the node
    that performs it -- never in the Write Guard node, which
    `interrupt_before` protects from re-execution but which measurement
    (M2b) showed does *not* protect the writing node itself. Returns the
    state the caller should act on: `"in_flight"` means proceed and write;
    `"confirmed"`/`"failed"` means the action was already settled and its
    stored result should be returned without a second write.
    """
    with pool.connection() as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE consents SET consumed_at = now()
                    WHERE action_id = %s AND consumed_at IS NULL
                    RETURNING action_id
                    """,
                    (action_id,),
                )
                if cur.fetchone() is None:
                    raise ConsentAlreadyConsumedError(action_id)

                cur.execute(
                    """
                    INSERT INTO idempotency_keys
                        (owner, cart_id, action_id, canonical_args_hash, state)
                    VALUES (%s, %s, %s, %s, 'in_flight')
                    ON CONFLICT (owner, cart_id, action_id) DO NOTHING
                    RETURNING state, canonical_args_hash
                    """,
                    (owner, cart_id, action_id, canonical_args_hash),
                )
                inserted = cur.fetchone()
                if inserted is not None:
                    return "in_flight"

                cur.execute(
                    """
                    SELECT state, canonical_args_hash FROM idempotency_keys
                    WHERE owner = %s AND cart_id = %s AND action_id = %s
                    """,
                    (owner, cart_id, action_id),
                )
                existing = cur.fetchone()
                assert existing is not None  # ON CONFLICT target guarantees a row
                if existing["canonical_args_hash"] != canonical_args_hash:
                    raise ActionAlreadyInFlightError(action_id)
                state: IdempotencyState = existing["state"]
                return state


def mark_action(
    pool: ConnectionPool,
    owner: str,
    cart_id: str,
    action_id: str,
    state: IdempotencyState,
) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE idempotency_keys SET state = %s, updated_at = now()
            WHERE owner = %s AND cart_id = %s AND action_id = %s
            """,
            (state, owner, cart_id, action_id),
        )


def save_receipt(pool: ConnectionPool, receipt: Receipt) -> None:
    """Upsert on `action_id` (D-G5-09): an `unverified` row written first
    (e.g. from a resume-time reconciliation) can be replaced by a
    `receipt` row once a later read-back confirms the outcome."""
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO receipts
                (action_id, session_id, owner, before_state, after_state, verified,
                 status, reason, expected_delta, actual_delta, trace_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (action_id) DO UPDATE SET
                before_state = EXCLUDED.before_state,
                after_state = EXCLUDED.after_state,
                verified = EXCLUDED.verified,
                status = EXCLUDED.status,
                reason = EXCLUDED.reason,
                expected_delta = EXCLUDED.expected_delta,
                actual_delta = EXCLUDED.actual_delta,
                trace_id = EXCLUDED.trace_id
            """,
            (
                receipt.action_id,
                receipt.session_id,
                receipt.owner,
                json.dumps(receipt.before_state, default=_json_default),
                json.dumps(receipt.after_state, default=_json_default),
                receipt.verified,
                receipt.status,
                receipt.reason,
                (
                    str(receipt.expected_delta)
                    if receipt.expected_delta is not None
                    else None
                ),
                (
                    str(receipt.actual_delta)
                    if receipt.actual_delta is not None
                    else None
                ),
                receipt.trace_id,
            ),
        )


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"not JSON-serializable for receipt storage: {type(value)}")
