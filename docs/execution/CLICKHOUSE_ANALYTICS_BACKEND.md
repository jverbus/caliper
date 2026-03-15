# ClickHouse analytics backend

This chunk adds a production-oriented analytics seam for event-heavy workloads using ClickHouse,
without making ClickHouse mandatory for local v1 operation.

## Implemented in PV1-006

- Added `ClickHouseAnalyticsStore` in `caliper_storage.clickhouse`.
- Added schema bootstrap helpers:
  - `ensure_schema()` creates the target database + MergeTree table.
- Added event ingest helper:
  - `append_event(event)` persists `EventEnvelope` rows with UTC timestamps and JSON payloads.
- Added job-level summary query helper:
  - `summarize_job(workspace_id, job_id)` returns event count, event-type cardinality, and first/last event timestamps.
- Exported analytics seam via `caliper_storage.__init__` for wiring from service runtimes.

## Runtime contract

The backend expects a minimal ClickHouse client surface:

- `command(query: str)`
- `insert(table: str, data: list[dict[str, Any]])`
- `query(query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]`

This keeps the seam compatible with either `clickhouse-connect` or a thin internal adapter.

## Acceptance mapping

- **ClickHouse backend seam exists and is injectable**: `ClickHouseAnalyticsStore` exposes explicit schema, write, and summary read APIs.
- **Unit-tested SQL behavior**: tests cover schema commands, append payload shape, and summary query interpretation.
- **No v1 local dependency regression**: no mandatory ClickHouse dependency added to base install; local SQLite/Postgres workflows remain unchanged.
