SHELL := /bin/bash
PY := uv run
PYTHONPATH := packages/py-caliper-core/src:packages/py-caliper-storage/src:packages/py-caliper-events/src:packages/py-caliper-policies/src:packages/py-caliper-reward/src:packages/py-caliper-reports/src:packages/py-caliper-adapters/src:packages/py-sdk/src:apps

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
	PYTHONPATH=$(PYTHONPATH) $(PY) python examples/workflow_demo/demo.py --mode embedded

demo-web:
	PYTHONPATH=$(PYTHONPATH) $(PY) python examples/web_demo/demo.py

demo-email:
	PYTHONPATH=$(PYTHONPATH) $(PY) python examples/email_demo/demo.py

run-embedded:
	PYTHONPATH=$(PYTHONPATH) $(PY) python scripts/run_embedded.py

run-service:
	PYTHONPATH=$(PYTHONPATH) $(PY) uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

run-worker:
	PYTHONPATH=$(PYTHONPATH) $(PY) python apps/worker/main.py

seed-demo-data:
	PYTHONPATH=$(PYTHONPATH) $(PY) python scripts/seed_demo_data.py
