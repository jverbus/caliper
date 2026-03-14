# Outcome ingest (`POST /v1/outcomes`)

Chunk: **P3-004 Outcome ingest**

## Summary

The outcome ingest endpoint records delayed/batched outcome events tied to a prior decision and emits a canonical `outcome.observed` ledger event for projections and downstream policy updates.

## Request contract

`POST /v1/outcomes` expects an `OutcomeCreate` payload:

- `workspace_id`
- `job_id`
- `decision_id`
- `unit_id`
- `events[]` (supports binary and numeric outcome values)
- `attribution_window.hours`
- optional `metadata`

Example event payload supports business outcomes plus cost/latency:

- `signup` (`value`: `1`)
- `token_cost_usd` (`value`: `0.03`)
- `p95_latency_seconds` (`value`: `1.2`)

## Behavior

1. Resolve request-hash idempotency for `/v1/outcomes` to ensure duplicate-safe retries.
2. Validate job exists and `workspace_id` matches the job scope.
3. Validate referenced decision exists and matches `workspace_id`, `job_id`, and `unit_id`.
4. Persist outcome payload to outcomes storage.
5. Emit `outcome.observed` event with:
   - `decision_id`
   - resolved `arm_id` from the source decision
   - full events list
   - attribution window and metadata
6. Persist idempotent response snapshot and append outcome audit entry.

## Guarantees

- Duplicate retries with identical payload return the original response without duplicate outcome rows.
- Delayed outcomes are accepted as long as decision context matches.
- Event payload includes `arm_id` to support projection rebuild outcome attribution.

## Test coverage

`tests/integration/test_api_outcomes.py` validates:

- persistence + duplicate-safe retries
- decision-context mismatch rejection
- unknown decision rejection
- canonical event emission with `arm_id`
