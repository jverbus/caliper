# Minimal operator UI

Implements a lightweight operator console for quick job visibility without requiring a full frontend stack.

## Deliverables

- `apps/operator_ui/main.py` FastAPI app serving HTML pages.
- `/jobs` page showing current jobs with workspace filter support (`?workspace_id=...`).
- `/healthz` endpoint for process checks.
- API support for listing jobs via `GET /v1/jobs` (optional `workspace_id` filter).

## Run

```bash
uv run uvicorn apps.operator_ui.main:app --reload --port 8010
```

Then open `http://127.0.0.1:8010/jobs`.

## Acceptance mapping

- Minimal operator UI exists and runs locally.
- Operators can see current jobs and key status fields without using raw SQL.
- Workspace-scoped inspection works via query parameter filtering.
