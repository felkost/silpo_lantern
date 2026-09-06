"""Non-regression test for a defect found at G1+G2 stage close: `import
deepeval` calls `load_dotenv()`, and because deepeval ships a pytest plugin
it was imported on every run. The whole `.env` therefore reached
`os.environ` before collection, with two consequences:

- the offline gate ran with real credentials in the environment, so its "no
  live call" guarantee rested on no test happening to read them rather than
  on the environment being clean;
- the integration tests' `skipif("DATABASE_URL" not in os.environ)` guard
  never fired on any machine with a `.env` file — `pytest tests/integration`
  reported 5 passed against live Neon where the developer expected 5 skipped.

`pyproject.toml` disables the plugin for every run in this repository; this
test pins that, because the failure is silent and env-dependent.
"""

import sys


def test_deepeval_plugin_is_not_loaded_during_the_gate() -> None:
    """deepeval must not be imported by the test run itself.

    If this fails, `addopts = "-p no:deepeval"` was dropped from
    `pyproject.toml` and `.env` is once again leaking into every test's
    environment.
    """
    assert "deepeval" not in sys.modules, (
        "deepeval is loaded; it calls load_dotenv() on import and will inject "
        ".env into os.environ for the whole session"
    )
