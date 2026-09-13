"""The Write Guard's own persistence: consents, the idempotency journal,
and receipts. Sync (`psycopg_pool.ConnectionPool`), deliberately separate
from `checkpointer.py`'s async pool -- the checkpointer serializes
`RecoveryState` across the LangGraph interrupt boundary, this module
authorizes and records one write. Both point at the same Neon database;
neither needs to know the other's connection.

kept sync on purpose. `apps/api` resumes the graph with
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
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterator, Literal, Optional, Tuple

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

# a guest who walks away leaves a live Silpo credential in
# a public service. Thirty minutes covers a full recovery session with a
# generous consent pause (CONSENT_TTL is five), and every token read
# restarts the clock, so a session in use never expires under the guest.
SESSION_IDLE_TTL = timedelta(minutes=30)


class ActionAlreadyInFlightError(Exception):
    """Raised by `claim_and_consume` when the journal row for this
    `(owner, cart_id, action_id)` already exists with a different
    `canonical_args_hash` -- the same logical action requested with
    different arguments, which the brief requires be rejected
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
    # `check`: a connection Neon dropped server-side (idle-suspend, a host
    # waking from sleep) looks open on the client until it is used -- the
    # first request after ~20 idle minutes answered 500 with "SSL connection
    # has been closed unexpectedly". The check is one round trip on
    # checkout and replaces the dead connection instead of handing it out.
    pool = ConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=MAX_POOL_SIZE,
        open=True,
        check=ConnectionPool.check_connection,
    )
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


def get_session(pool: ConnectionPool, session_id: str) -> Optional[Dict[str, str]]:
    """looks up a session's own `owner` -- needed by `GET
    /session/{id}/events` the FIRST time it is called for a session,
    before any graph checkpoint exists to read `owner` back from."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT session_id, thread_id, owner FROM sessions"
                " WHERE session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    # Same UUID-column conversion as `load_consent`: without it this
    # function's own `Dict[str, str]` annotation is false for `session_id`.
    return {key: str(value) for key, value in row.items()}


def save_session_token(
    pool: ConnectionPool, session_id: str, token: Dict[str, Any]
) -> None:
    """Stores (or replaces) the OAuth token the guest of THIS session
    authorised. Upsert, not insert: re-authorising an existing session
    (an expired token, a fresh consent screen) must replace the old
    credential rather than fail on the primary key."""
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO oauth_tokens (session_id, token)
            VALUES (%s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                token = EXCLUDED.token,
                updated_at = now()
            """,
            (session_id, json.dumps(token)),
        )


def load_session_token(
    pool: ConnectionPool, session_id: str
) -> Optional[Dict[str, Any]]:
    """Idle expiry lives here, on the read path, because every use of the
    credential -- each MCP call -- comes through it: a row idle past
    `SESSION_IDLE_TTL` is deleted and reported absent, a live one is
    touched. Both against Postgres's own clock, so container
    clock skew can neither kill a live session nor resurrect a dead one."""
    with pool.connection() as conn:
        conn.execute(
            "DELETE FROM oauth_tokens WHERE session_id = %s"
            " AND updated_at <= now() - %s",
            (session_id, SESSION_IDLE_TTL),
        )
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "UPDATE oauth_tokens SET updated_at = now()"
                " WHERE session_id = %s RETURNING token",
                (session_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    token: Dict[str, Any] = row["token"]
    return token


def move_session_token(pool: ConnectionPool, old_id: str, new_id: str) -> bool:
    """«Перевірити знову»: one recovery run is one session (the graph's
    checkpoint is keyed by the session's thread), so a second check needs
    a second session -- but not a second login. The credential moves to
    the new session row in one transaction; the old session keeps its
    consents and receipts and loses only the token, exactly as a logout
    would. Returns False when the old session holds no live credential."""
    with pool.connection() as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "DELETE FROM oauth_tokens WHERE session_id = %s RETURNING token",
                    (old_id,),
                )
                row = cur.fetchone()
            if row is None:
                return False
            conn.execute(
                "INSERT INTO oauth_tokens (session_id, token) VALUES (%s, %s)",
                (new_id, json.dumps(row["token"])),
            )
    return True


def delete_session_token(pool: ConnectionPool, session_id: str) -> None:
    """logout. Removes the credential and nothing else --
    the `sessions` row stays because `consents`/`receipts` reference it
    without cascade (0003, 0005): deleting it would fail on the FK, and a
    cascade there would destroy the audit trail a logout must not touch."""
    with pool.connection() as conn:
        conn.execute("DELETE FROM oauth_tokens WHERE session_id = %s", (session_id,))


def save_consent(pool: ConnectionPool, consent: ConsentRecord) -> None:
    """`ON CONFLICT (action_id) DO NOTHING` -- a double-clicked
    consent button, or a retried request, used to raise a bare primary-key
    violation and 500 the endpoint. the mandatory RG variants name
    «подвійний клік» explicitly, so this is an RG obligation, not a nicety.
    A second call with the SAME `action_id` is, by construction, consent to
    the same proposal (the API recomputes both hashes server-side from the
    session's own state before calling this, so nothing here can silently
    diverge) -- the correct response to a duplicate is to leave the first
    row standing, not to overwrite or reject it.
    """
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO consents
                (action_id, session_id, owner, cart_id, canonical_args, args_hash,
                 state_hash, prompt_version, policy_version, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (action_id) DO NOTHING
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
    the row is stamped by Postgres's own `now()`, and a few
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
    # `action_id`/`session_id` are UUID columns, so psycopg hands them back
    # as `uuid.UUID`, while every id in the domain layer is a `str` -- the
    # conversion belongs here, at the boundary that turns rows into domain
    # objects, not in the guard that consumes them.
    record = ConsentRecord(
        action_id=str(row["action_id"]),
        session_id=str(row["session_id"]),
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
) -> Tuple[bool, IdempotencyState]:
    """the idempotency claim and the consent consumption happen
    in one transaction, immediately before the write call, inside the node
    that performs it -- never in the Write Guard node, which
    `interrupt_before` protects from re-execution but which measurement
    (M2b) showed does *not* protect the writing node itself.

    Returns `(just_claimed, state)`. `just_claimed=True` means THIS call
    created the journal row -- the caller must proceed to the actual
    write. `just_claimed=False` means an EARLIER call already claimed
    this action (a resume after a crash, or a genuine duplicate request);
    `state` is whatever that earlier call left behind, and the caller
    must NEVER write again, only reconcile from a read-back.

    The idempotency INSERT happens *before* consuming the consent, and
    only the caller that wins the `ON CONFLICT` race touches
    `consents.consumed_at` at all -- a corrected ordering from this
    stage's own first draft, which consumed the consent unconditionally
    and made a resumed reconciliation attempt raise
    `ConsentAlreadyConsumedError` instead of ever reaching the
    already-existed branch below (found while writing this module's own
    resume test, not in production).
    """
    with pool.connection() as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO idempotency_keys
                        (owner, cart_id, action_id, canonical_args_hash, state)
                    VALUES (%s, %s, %s, %s, 'in_flight')
                    ON CONFLICT (owner, cart_id, action_id) DO NOTHING
                    RETURNING state
                    """,
                    (owner, cart_id, action_id, canonical_args_hash),
                )
                just_inserted = cur.fetchone()
                if just_inserted is not None:
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
                    return True, "in_flight"

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
                return False, state


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
    """Upsert on `action_id`: an `unverified` row written first
    (e.g. from a resume-time reconciliation) can be replaced by a
    `receipt` row once a later read-back confirms the outcome."""
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO receipts
                (action_id, session_id, owner, before_state, after_state, verified,
                 status, reason, expected_delta, actual_delta, trace_id,
                 blocker_cleared, remaining_gap, kind)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (action_id) DO UPDATE SET
                before_state = EXCLUDED.before_state,
                after_state = EXCLUDED.after_state,
                verified = EXCLUDED.verified,
                status = EXCLUDED.status,
                reason = EXCLUDED.reason,
                expected_delta = EXCLUDED.expected_delta,
                actual_delta = EXCLUDED.actual_delta,
                trace_id = EXCLUDED.trace_id,
                blocker_cleared = EXCLUDED.blocker_cleared,
                remaining_gap = EXCLUDED.remaining_gap,
                kind = EXCLUDED.kind
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
                receipt.blocker_cleared,
                (
                    str(receipt.remaining_gap)
                    if receipt.remaining_gap is not None
                    else None
                ),
                receipt.kind,
            ),
        )


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"not JSON-serializable for receipt storage: {type(value)}")
