"""Kernel layer: settings and constants only, no project-local imports.
Every other layer may depend on this one; this one depends on nothing in
`src.lantern`.
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
    """The SQLAlchemy-dialect Neon DSN, loading `.env` first.

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


def get_openrouter_api_key(env_path: Optional[Path] = None) -> str:
    """The OpenRouter API key for planner/explainer LLM calls."""
    load_env(env_path)
    try:
        return os.environ["OPENROUTER_API_KEY"]
    except KeyError as exc:
        raise MissingSettingError(
            f"OPENROUTER_API_KEY is set neither in the environment nor in "
            f"{env_path or DEFAULT_ENV_PATH}"
        ) from exc


def get_owner_secret(env_path: Optional[Path] = None) -> str:
    """G5+G6 (D-G5-06): a server-side secret mixed into the derived
    `owner` hash when the cached MCP OAuth token carries no stable
    subject claim (measured live — probe P2 — that it does not). Never
    derived from `cart_id`: `compute_state_hash` already includes
    `cart_id`, so an owner derived from it would make an owner-mismatch
    check vacuous."""
    load_env(env_path)
    try:
        return os.environ["LANTERN_OWNER_SECRET"]
    except KeyError as exc:
        raise MissingSettingError(
            f"LANTERN_OWNER_SECRET is set neither in the environment nor in "
            f"{env_path or DEFAULT_ENV_PATH}"
        ) from exc


def strip_sqlalchemy_dialect(url: str) -> str:
    """Derive the bare `postgresql://` DSN `langgraph-checkpoint-postgres`
    needs from the SQLAlchemy-dialect `DATABASE_URL`. Fails loud on
    any shape other than the one exact prefix this project actually uses
    (psycopg 3) — a silent pass-through would let a future DSN-format
    drift reach the checkpointer as a much less diagnosable error.
    """
    if not url.startswith(_SQLALCHEMY_PSYCOPG_PREFIX):
        raise ValueError(
            f"expected a DSN starting with {_SQLALCHEMY_PSYCOPG_PREFIX!r}, got: {url!r}"
        )
    return _BARE_POSTGRES_PREFIX + url[len(_SQLALCHEMY_PSYCOPG_PREFIX) :]
