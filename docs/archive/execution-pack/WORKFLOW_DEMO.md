# Workflow demo and docs (P5-004)

This chunk turns the workflow adapter into an end-to-end runnable demo in both deployment modes.

## What ships

- A realistic demo implementation at `examples/workflow_demo/demo.py`
- `make demo-workflow` support (embedded mode)
- Checked-in sample report fixtures under `docs/fixtures/workflow_demo/`
- Integration coverage proving the demo runs in embedded mode and service mode

## Run the demo (embedded mode)

```bash
make demo-workflow
```

Equivalent direct invocation:

```bash
uv run python examples/workflow_demo/demo.py --mode embedded
```

Artifacts are written to:

- `docs/fixtures/workflow_demo/embedded/report.json`
- `docs/fixtures/workflow_demo/embedded/report.md`
- `docs/fixtures/workflow_demo/embedded/report.html`

## Run the demo (service mode)

Start API service:

```bash
CALIPER_PROFILE=embedded CALIPER_DB_URL=sqlite:///./data/workflow-demo-service.db \
  uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Then run the workflow demo against it:

```bash
uv run python examples/workflow_demo/demo.py --mode service --api-url http://127.0.0.1:8000
```

Service-mode artifacts are written to:

- `docs/fixtures/workflow_demo/service/report.json`
- `docs/fixtures/workflow_demo/service/report.md`
- `docs/fixtures/workflow_demo/service/report.html`

## Demo shape

The demo:

1. Creates a workflow-surface job with fixed-split policy
2. Registers two prompt arms (`arm-fast`, `arm-accurate`)
3. Executes 10 workflow units through `WorkflowAdapter`
4. Logs exposure + objective/latency/cost outcomes + optional human acceptance outcomes
5. Generates and persists a report

## Acceptance mapping

- **`examples/workflow_demo` exists and is runnable:** `examples/workflow_demo/demo.py`
- **`make demo-workflow` works:** Make target executes the demo in embedded mode
- **Sample reports checked into docs/fixtures:** `docs/fixtures/workflow_demo/*`
- **Demo passes in embedded mode and service mode:** `tests/integration/test_workflow_demo.py`
