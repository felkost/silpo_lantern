"""The DDL requirement (sessions, consents, receipts, idempotency_keys,
schema version) covered by a tiny runner over plain SQL files, tracked in
its own `schema_migrations` table (separate from LangGraph's own
`checkpoint_migrations`, which `AsyncPostgresSaver.setup()` owns entirely).
Applying the same migration set twice must not error, same idempotency
discipline as the checkpointer's own `.setup()`.
"""

import os

import psycopg
import pytest

from src.lantern.config import strip_sqlalchemy_dialect
from src.lantern.memory.migrations_runner import run_migrations

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


async def test_migrations_apply_and_are_idempotent() -> None:
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])

    await run_migrations(dsn)
    await run_migrations(dsn)  # must not error the second time

    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        async with conn.cursor() as cur:
            for table in (
                "sessions",
                "consents",
                "receipts",
                "idempotency_keys",
                "schema_version",
            ):
                await cur.execute(
                    "SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",)
                )
                (exists,) = await cur.fetchone()
                assert exists, f"table {table} was not created by the migrations"
