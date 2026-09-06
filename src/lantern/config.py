"""Kernel layer: settings and constants only, no project-local imports
(CLAUDE.md architecture table). Every other layer may depend on this one;
this one depends on nothing in `src.lantern`.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

_SQLALCHEMY_PSYCOPG_PREFIX = "postgresql+psycopg://"
_BARE_POSTGRES_PREFIX = "postgresql://"


class MissingSettingError(RuntimeError):
    """A required setting is absent from both the environment and `.env`.

    Raised instead of a bare `KeyError` because the original defect surfaced
    as `KeyError: 'DATABASE_URL'` from inside a FastAPI lifespan, which says
    nothing about which file was expected to supply it.
    """


def load_env(path: Optional[Path] = None) -> None:
    """Load `.env` into the process environment, without overriding anything
    already set. Called by the accessors below rather than at import time, so
    importing this module stays free of file I/O and a test's environment is
    never silently replaced by the developer's own `.env`.
    """
    load_dotenv(path or DEFAULT_ENV_PATH, override=False)


def get_database_url(env_path: Optional[Path] = None) -> str:
    """The SQLAlchemy-dialect Neon DSN (D15), loading `.env` first.

    The loading lives here, in the accessor, because a caller that reads the
    variable directly is exactly the defect this replaced: `uvicorn
    apps.api.main:app` crashed on a bare `KeyError` whenever the shell had
    not sourced `.env` by hand.
    """
    load_env(env_path)
    try:
        return os.environ["DATABASE_URL"]
    except KeyError as exc:
        raise MissingSettingError(
            f"DATABASE_URL is set neither in the environment nor in "
            f"{env_path or DEFAULT_ENV_PATH}"
        ) from exc


def strip_sqlalchemy_dialect(url: str) -> str:
    """Derive the bare `postgresql://` DSN `langgraph-checkpoint-postgres`
    needs from the SQLAlchemy-dialect `DATABASE_URL` (D-G1-01). Fails loud on
    any shape other than the one exact prefix this project actually uses
    (psycopg 3, per D15) — a silent pass-through would let a future DSN-format
    drift reach the checkpointer as a much less diagnosable error (R8).
    """
    if not url.startswith(_SQLALCHEMY_PSYCOPG_PREFIX):
        raise ValueError(
            f"expected a DSN starting with {_SQLALCHEMY_PSYCOPG_PREFIX!r}, got: {url!r}"
        )
    return _BARE_POSTGRES_PREFIX + url[len(_SQLALCHEMY_PSYCOPG_PREFIX) :]
