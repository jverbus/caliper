# Web demo (P6-003)

This chunk turns the web adapter into an end-to-end demo that exercises request-time assignment and distinct render/click/conversion telemetry.

## What ships

- Runnable web demo implementation at `examples/web_demo/demo.py`
- `make demo-web` support (embedded mode)
- Checked-in sample report fixtures under `docs/fixtures/web_demo/`
- Integration coverage proving the demo runs in embedded mode and service mode

## Run the demo (embedded mode)

```bash
make demo-web
```

Equivalent direct invocation:

```bash
uv run python examples/web_demo/demo.py --mode embedded
```

Artifacts are written to:

- `docs/fixtures/web_demo/embedded/report.json`
- `docs/fixtures/web_demo/embedded/report.md`
- `docs/fixtures/web_demo/embedded/report.html`

## Run the demo (service mode)

Start API service:

```bash
CALIPER_PROFILE=embedded CALIPER_DB_URL=sqlite:///./data/web-demo-service.db \
  uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Then run the web demo against it:

```bash
uv run python examples/web_demo/demo.py --mode service --api-url http://127.0.0.1:8000
```

Service-mode artifacts are written to:

- `docs/fixtures/web_demo/service/report.json`
- `docs/fixtures/web_demo/service/report.md`
- `docs/fixtures/web_demo/service/report.html`

## Demo shape

The demo:

1. Creates a web-surface job with segment dimensions (`country`, `device`)
2. Registers two landing-page arms
3. Executes 12 request-time assignments through `WebAdapter`
4. Logs render exposure separately from click/conversion outcomes
5. Generates and persists a report with segment findings

## Acceptance mapping

- **`examples/web_demo` exists and is runnable:** `examples/web_demo/demo.py`
- **`make demo-web` works:** Make target executes the demo in embedded mode
- **Segment-aware report example exists:** `docs/fixtures/web_demo/*`
- **Demo shows request-time assignment and segment findings:** `tests/integration/test_web_demo.py`
