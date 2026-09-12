"""T10: `repository.IdempotencyState`'s members must
equal the SQL `CHECK` constraint's own list, parsed from the migration
file directly -- not re-typed by hand, which is exactly the kind of
duplicated literal an earlier retrospective of this project flags as a
recurring source of silent drift.
"""

import re
import typing

from src.lantern.config import PROJECT_ROOT
from src.lantern.memory.repository import IdempotencyState

_MIGRATION_PATH = (
    PROJECT_ROOT
    / "src"
    / "lantern"
    / "memory"
    / "migrations"
    / "0004_idempotency_keys.sql"
)


def test_idempotency_state_literal_matches_sql_check() -> None:
    text = _MIGRATION_PATH.read_text(encoding="utf-8")
    match = re.search(r"state IN \(([^)]+)\)", text)
    assert match is not None, "CHECK constraint not found in migration file"
    sql_states = {s.strip().strip("'") for s in match.group(1).split(",")}

    literal_states = set(typing.get_args(IdempotencyState))

    assert literal_states == sql_states
