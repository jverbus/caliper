# P3-006 Report generation

## Scope

Implements deterministic report generation for a job with:

- JSON report payload (`ReportPayload`)
- Human-readable Markdown and HTML renderings
- Latest report retrieval API

## API

- `POST /v1/jobs/{job_id}/reports:generate`
  - validates workspace and job scope
  - gathers arms, decisions, exposures, outcomes, guardrails
  - generates and persists a report run
  - appends `report.generated` audit record
- `GET /v1/jobs/{job_id}/reports/latest?workspace_id=...`
  - returns the most recent persisted report

## Output sections

Each generated report includes:

- leaders
- traffic shifts
- guardrails
- segment findings
- recommendations
- markdown
- html

## Storage

Report runs persist in `report_runs` with serialized payload for deterministic retrieval.
