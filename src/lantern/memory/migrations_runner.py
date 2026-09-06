"""A tiny runner over plain SQL files — a handful of `CREATE TABLE IF NOT
EXISTS` statements need no migration-framework dependency. Files are named
`NNNN_description.sql`, applied in filename order, tracked in this
project's own `schema_migrations` table — separate from LangGraph's
`checkpoint_migrations`, which `AsyncPostgresSaver.setup()` owns entirely
and this runner never touches.
"""

from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


async def run_migrations(dsn: str) -> None:
    """Applies every `*.sql` file under `migrations/` not yet recorded in
    `schema_migrations`, in filename order. Safe to call repeatedly.
    """
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """)
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                await cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE filename = %s", (path.name,)
                )
                if await cur.fetchone() is not None:
                    continue
                await cur.execute(path.read_text(encoding="utf-8"))
                await cur.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
                )
