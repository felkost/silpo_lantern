"""Non-regression test for a real defect: `uvicorn
apps.api.main:app` (the exact command named as the "App starts"
criterion, and the one `make run` issues) crashed with a bare
`KeyError: 'DATABASE_URL'`. The tests had passed only because the shell had
sourced `.env` first — nothing in the application itself ever loaded it,
even though `python-dotenv` was already a pinned dependency.

The fix puts the loading inside the accessor, so a caller cannot read the
setting without it having been loaded.
"""

import os
from pathlib import Path

import pytest

from src.lantern.config import MissingSettingError, get_database_url, load_env


def test_load_env_reads_a_dotenv_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql+psycopg://u:p@example/db\n", encoding="utf-8"
    )

    load_env(env_file)

    assert os.environ["DATABASE_URL"] == "postgresql+psycopg://u:p@example/db"


def test_load_env_does_not_override_an_already_set_variable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://real:one@host/db")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql+psycopg://file:value@host/db\n", encoding="utf-8"
    )

    load_env(env_file)

    assert os.environ["DATABASE_URL"] == "postgresql+psycopg://real:one@host/db"


def test_get_database_url_loads_the_env_file_itself(
    tmp_path: Path, monkeypatch
) -> None:
    """The accessor must work with nothing pre-sourced into the shell — this
    is the exact path that failed under uvicorn.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql+psycopg://u:p@example/db\n", encoding="utf-8"
    )

    assert get_database_url(env_file) == "postgresql+psycopg://u:p@example/db"


def test_get_database_url_raises_a_named_error_when_unset(
    tmp_path: Path, monkeypatch
) -> None:
    """A bare KeyError deep inside a lifespan is not a diagnosable failure."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(MissingSettingError):
        get_database_url(tmp_path / "does-not-exist.env")
