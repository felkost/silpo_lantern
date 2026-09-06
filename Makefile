.PHONY: gate test test-integration lint secret-scan report openapi run eval

gate: lint test

lint:
	black --check . tests/*.py
	flake8
	mypy src apps

test:
	pytest -q tests/unit tests/contract

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

eval:
	@echo "Not available yet — DeepEval wiring lands at G8+G9 (plan section 12/13)."
	@exit 1
