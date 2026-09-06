"""The checkpointer needs a bare
`postgresql://` DSN, but `DATABASE_URL` stays in its SQLAlchemy-dialect form
(`postgresql+psycopg://`) as the single source of truth. One pure
conversion function is the only place that translates between the two, so the
checkpointer and the SQLAlchemy engine can never silently drift onto two
different connection strings.
"""

import pytest

from src.lantern.config import strip_sqlalchemy_dialect


def test_strips_the_sqlalchemy_psycopg_dialect_prefix() -> None:
    url = "postgresql+psycopg://user:pass@ep-example.eu-central-1.aws.neon.tech/lantern"
    assert strip_sqlalchemy_dialect(url) == (
        "postgresql://user:pass@ep-example.eu-central-1.aws.neon.tech/lantern"
    )


def test_preserves_query_parameters() -> None:
    url = "postgresql+psycopg://u:p@host/db?sslmode=require"
    assert strip_sqlalchemy_dialect(url) == "postgresql://u:p@host/db?sslmode=require"


def test_rejects_a_dsn_already_missing_the_dialect_suffix() -> None:
    """Fail loud rather than silently pass through a DSN shape the
    checkpointer would reject anyway with a less diagnosable error.
    """
    with pytest.raises(ValueError):
        strip_sqlalchemy_dialect("postgresql://u:p@host/db")


def test_rejects_an_unexpected_dialect_suffix() -> None:
    """R8: a future `+psycopg2` (or any other) suffix must fail loud at
    startup, not be silently mishandled.
    """
    with pytest.raises(ValueError):
        strip_sqlalchemy_dialect("postgresql+psycopg2://u:p@host/db")
