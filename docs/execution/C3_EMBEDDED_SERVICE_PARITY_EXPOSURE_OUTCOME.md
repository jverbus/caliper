# C3: embedded/service parity for exposure+outcome logical flow

This chunk hardens embedded SDK parity with service-mode API behavior for exposure/outcome ingest.

## What changed

- `EmbeddedCaliperClient.log_exposure` now matches service semantics:
  - validates job existence and workspace ownership,
  - validates decision existence and `(workspace_id, job_id, unit_id)` consistency,
  - applies idempotent replay via request-hash keying,
  - appends `decision.exposed` to the event ledger,
  - appends `decision.exposed` audit records.
- `EmbeddedCaliperClient.log_outcome` now matches service semantics:
  - validates job/decision context consistency,
  - applies idempotent replay via request-hash keying,
  - appends `outcome.observed` to the event ledger (with arm linkage + event payloads),
  - appends `outcome.observed` audit records.
- Added shared embedded-client helper paths for idempotent create + decision-context validation.

## Why

Before this chunk, service mode enforced stricter exposure/outcome ingest guarantees than embedded mode. That created drift risk in replay, auditability, and operational behavior across deployment styles.

This chunk closes the parity gap so embedded and service flows now align on:

- decision-context validation,
- idempotent ingest behavior,
- event ledger append semantics,
- audit trail coverage.

## Validation

- Extended SDK unit coverage to assert:
  - duplicate exposure/outcome ingest is idempotent,
  - ledger/audit entries are emitted once under replay,
  - context mismatches are rejected for both exposures and outcomes.
- Full project gates:
  - `make lint`
  - `make typecheck`
  - `make test`
