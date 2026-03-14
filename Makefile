SHELL := /bin/bash
PY := uv run

.PHONY: setup lint format typecheck test test-unit test-integration test-property \
	demo-workflow demo-web demo-email run-embedded run-service run-worker seed-demo-data

setup:
	uv sync --group dev
	pnpm install

lint:
	$(PY) ruff check .
	pnpm lint

format:
	$(PY) ruff format .

# Keep typecheck separate from lint for CI matrix flexibility.
typecheck:
	$(PY) mypy packages apps tests
	pnpm typecheck

test:
	$(PY) pytest tests

test-unit:
	$(PY) pytest tests/unit

test-integration:
	$(PY) pytest tests/integration

test-property:
	$(PY) pytest tests/property

demo-workflow:
	$(PY) python examples/workflow_demo/demo.py

demo-web:
	$(PY) python examples/web_demo/demo.py

demo-email:
	$(PY) python examples/email_demo/demo.py

run-embedded:
	$(PY) python scripts/run_embedded.py

run-service:
	$(PY) uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

run-worker:
	$(PY) python apps/worker/main.py

seed-demo-data:
	$(PY) python scripts/seed_demo_data.py
