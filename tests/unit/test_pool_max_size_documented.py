"""F14 (docs/g1-g2-stage-spec.md, round 2): the checkpointer's
`AsyncConnectionPool` size is an explicit, documented constant — not left as
an unstated guess — and stays under Neon free tier's own connection ceiling
(already a named risk in the plan itself, section 9/IV-02).
"""

from src.lantern.memory.checkpointer import (
    MAX_POOL_SIZE,
    NEON_FREE_TIER_CONNECTION_CEILING,
)


def test_max_pool_size_is_explicitly_set() -> None:
    assert isinstance(MAX_POOL_SIZE, int)
    assert MAX_POOL_SIZE > 0


def test_max_pool_size_stays_under_the_documented_neon_ceiling() -> None:
    assert MAX_POOL_SIZE < NEON_FREE_TIER_CONNECTION_CEILING
