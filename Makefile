.PHONY: gate test lint secret-scan report run eval

gate: lint test

lint:
	black --check . tests/*.py
	flake8
	mypy src

test:
	pytest -q

secret-scan:
	python scripts/secret_scan.py

report:
	@if [ -z "$(GATE)" ]; then echo "Usage: make report GATE=S0"; exit 1; fi
	python scripts/render_report.py --gate $(GATE)

run:
	@echo "Not available yet — apps/api and apps/web get a runnable server at G1."
	@exit 1

eval:
	@echo "Not available yet — DeepEval wiring lands at G8+G9 (plan section 12/13)."
	@exit 1
