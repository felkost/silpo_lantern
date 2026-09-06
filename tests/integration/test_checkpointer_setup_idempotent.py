"""F2 (docs/g1-g2-stage-spec.md): `AsyncPostgresSaver.setup()` is not
implicit (measured) — a missed call site fails deep inside a live user
request. Confirms it's safe to call across repeated process lifetimes
(opening and closing the pool twice), not just once.
"""

import os

import pytest

from src.lantern.config import strip_sqlalchemy_dialect
from src.lantern.memory.checkpointer import get_checkpointer

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set — see D-G1-04"
)


@pytest.mark.asyncio
async def test_setup_is_idempotent_across_repeated_pool_lifetimes() -> None:
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])

    async with get_checkpointer(dsn) as saver:
        assert saver is not None

    # A second, independent pool lifetime against the same DSN must not
    # error on tables the first lifetime already created.
    async with get_checkpointer(dsn) as saver:
        results = [
            item
            async for item in saver.alist(
                {"configurable": {"thread_id": "does-not-exist"}}
            )
        ]
        assert results == []
