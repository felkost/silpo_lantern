"""LangGraph checkpointer over Neon Postgres (D-G1-02, revised in round 2):
`AsyncPostgresSaver` built over an `AsyncConnectionPool`, not
`from_conn_string`'s single held connection — a single connection has no
reconnect path and no defense against Neon's own idle-suspend behavior
(measured live by the sdk-prober; see the G1+G2 stage spec).
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

# F14/R7: Neon free tier's own connection ceiling
# is already a named risk in the plan itself (section 9/IV-02). Kept small
# and explicit here rather than left as an unstated guess — not load-tested
# against real concurrent-session counts yet.
# ponytail: guessed default, revisit once G4+ live runs show real
# concurrent-session counts (R7).
MAX_POOL_SIZE = 5
NEON_FREE_TIER_CONNECTION_CEILING = 20


@asynccontextmanager
async def get_checkpointer(checkpointer_dsn: str) -> AsyncIterator[AsyncPostgresSaver]:
    """Opens the pool, runs `.setup()` once (not implicit — measured), and
    closes the pool on exit. `.setup()` obtains its connection implicitly
    through the pool passed as `conn` — no separate checkout needed
    (confirmed by direct probe against the installed SDK).
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
        saver = AsyncPostgresSaver(conn=pool)  # type: ignore[arg-type]
        await saver.setup()
        yield saver
    finally:
        await pool.close()
