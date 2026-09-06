"""Load `.env` before the integration modules evaluate their skip guards.

Two measured reasons this lives here rather than in the shell:

- `source .env` is not a reliable loader on this project's own Windows/Git
  Bash setup: the Neon DSN contains `&` in its query string, which bash
  interprets rather than assigning, so `DATABASE_URL` silently never reaches
  the environment.
- Until G1+G2 close, the variable arrived by accident anyway — `deepeval`'s
  pytest plugin called `load_dotenv()` on import. That is now disabled
  (`pyproject.toml`), so the loading has to be deliberate.

This runs at collection time, before each test module's module-level
`skipif` is evaluated, so a developer with a `.env` gets the live run and a
developer with neither `.env` nor an exported variable gets clean skips.
"""

from src.lantern.config import load_env

load_env()
