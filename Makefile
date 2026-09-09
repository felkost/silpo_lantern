.PHONY: gate test test-integration lint secret-scan report openapi run eval

gate: lint test

lint:
	black --check . tests/*.py
	flake8
	mypy src apps

test:
	pytest -q tests/unit tests/contract tests/e2e tests/golden tests/support

# D-G1-04: needs a real Neon Postgres (DATABASE_URL
# in the environment) — never part of `make gate`/CI, which has no reachable
# Postgres. Skips cleanly, per-test, when DATABASE_URL is unset.
test-integration:
	pytest -q tests/integration

secret-scan:
	python scripts/secret_scan.py

report:
	python scripts/render_report.py

# D-G1-07: dumps FastAPI's own generated OpenAPI schema for review/diffing —
# never hand-authored separately, so it can't silently drift from the routes.
openapi:
	python -c "import json; from apps.api.main import app; json.dump(app.openapi(), open('apps/api/openapi.json', 'w'), indent=2)"

# `python -m apps.api`, not a bare `uvicorn apps.api.main:app`: on Windows
# uvicorn builds its event loop before importing the app, so the selector-loop
# policy psycopg's async mode requires has to be set in the launcher first
# (measured at G1+G2 close — see apps/api/__main__.py).
run:
	python -m apps.api

# G9 (G9.5): re-enables the deepeval pytest plugin for THIS invocation
# only — pyproject.toml's `addopts = "-p no:deepeval"` disables it
# everywhere else, because `import deepeval` calls load_dotenv() and would
# leak the whole .env into every gate run otherwise
# (tests/unit/test_env_isolation.py pins that). tests/evals/ is excluded
# from `make test`'s scope for the same reason.
eval:
	pytest -q tests/evals -p deepeval
