"""LangGraph checkpointer over Neon Postgres: `AsyncPostgresSaver` built
over an `AsyncConnectionPool`, not `from_conn_string`'s single held
connection — a single connection has no reconnect path and no defense
against Neon's own idle-suspend behavior (measured live by the
sdk-prober).
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.base import SerializerProtocol
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

# Neon free tier's own connection ceiling. Kept small and explicit here
# rather than left as an unstated guess — not load-tested against real
# concurrent-session counts yet.
# ponytail: guessed default, revisit once live runs show real
# concurrent-session counts.
MAX_POOL_SIZE = 5
NEON_FREE_TIER_CONNECTION_CEILING = 20


@asynccontextmanager
async def get_checkpointer(
    checkpointer_dsn: str, serde: Optional[SerializerProtocol] = None
) -> AsyncIterator[AsyncPostgresSaver]:
    """Opens the pool, runs `.setup()` once (not implicit — measured), and
    closes the pool on exit. `.setup()` obtains its connection implicitly
    through the pool passed as `conn` — no separate checkout needed
    (confirmed by direct probe against the installed SDK).

    `serde` defaults to the SDK's own `JsonPlusSerializer` (via
    `AsyncPostgresSaver`'s own default) when omitted — this module stays
    generic infra with no opinion on what state shape it stores. The
    default serde logs "Deserializing unregistered type ... This will be
    blocked in a future version" for any project-defined Pydantic model it
    hasn't been told about, measured live against this project's own
    `ActionProposal`/`EvidenceTuple`, not a hypothetical. A caller
    checkpointing `RecoveryState` must pass
    `src.lantern.graph.state.recovery_state_serde()` here — this module
    cannot default to that itself without importing the `application` layer
    from `infra`, which the layering test forbids.
    """
    # row_factory=dict_row, autocommit=True: matches what `from_conn_string`
    # sets up internally for a single connection (measured by the
    # sdk-prober) — the pooled form needs the same connection shape.
    pool = AsyncConnectionPool(
        conninfo=checkpointer_dsn,
        min_size=1,
        max_size=MAX_POOL_SIZE,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    await pool.open()
    try:
        # mypy cannot infer the pool's row-factory generic from the runtime
        # `kwargs={"row_factory": dict_row}` above — the shape is correct
        # (confirmed by direct probe against the installed SDK), only the
        # static type parameter isn't derivable from a kwargs dict.
        saver = AsyncPostgresSaver(conn=pool, serde=serde)  # type: ignore[arg-type]
        await saver.setup()
        yield saver
    finally:
        await pool.close()
