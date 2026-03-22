# Testing and Acceptance Spec

This document defines the tests, demo scenarios, and release gates that OpenClaw must satisfy.

## 1. Testing philosophy

Caliper cannot rely on “it seems to work.” It must prove:

- decision correctness,
- idempotent ingest,
- joinability across events,
- reproducible reports,
- and safe adaptive behavior.

## 2. Required test layers

### 2.1 Unit tests

Cover:

- domain model validation,
- policy math,
- reward formulas,
- guardrail evaluation,
- report rendering,
- config parsing,
- idempotency helpers.

### 2.2 Integration tests

Cover:

- API create/read/update flows,
- decision to exposure to outcome joins,
- SQLite backend behavior,
- Postgres backend behavior,
- projection rebuilds,
- policy snapshot activation,
- pause and rollback flows.

### 2.3 Property tests

Cover:

- probability normalization,
- decision invariants,
- idempotency replay invariants,
- arm eligibility constraints,
- reward aggregation invariants.

### 2.4 Replay tests

Mandatory once contextual-ready work begins.

Cover:

- replay dataset integrity,
- deterministic snapshot use,
- decision envelope completeness.

### 2.5 Load or smoke tests

Cover:

- basic assignment throughput under local service mode,
- worker behavior under bursty outcome ingest,
- report generation on moderate fixture data.

V1 only needs pragmatic smoke targets, not heroic scale benchmarks.

## 3. Mandatory command contract

The following must exist and pass before release:

- `make lint`
- `make typecheck`
- `make test`
- `make test-integration`
- `make demo-workflow`
- `make demo-web`
- `make demo-email`

## 4. Policy-specific required tests

Every built-in policy must pass:

- cold-start behavior test,
- arm-addition test,
- arm-retirement test,
- deterministic seeded simulation test,
- sanity check that the policy prefers a consistently better arm in simulation,
- probability and propensity validity test.

## 5. Event and audit required tests

The platform must pass tests showing:

- every decision gets a stable ID,
- exposures can be joined to decisions,
- outcomes can be joined to decisions,
- duplicate writes are handled safely,
- reports reference the correct window and policy versions,
- audit log captures job and policy changes.

## 6. Black-box acceptance demos

### 6.1 Demo A — workflow

Scenario:

- create a workflow job with 3 arms
- use Thompson sampling or epsilon-greedy
- simulate outcomes including cost and latency
- generate a report
- show pause or promote flow

Pass criteria:

- traffic shifts toward a better arm
- decision IDs and propensities are logged
- report explains the shift
- embedded mode works

### 6.2 Demo B — web

Scenario:

- create a web job
- register several variants
- simulate request-time assignment and render
- log views, clicks, conversions
- generate report

Pass criteria:

- remote HTTP flow works
- exposure is distinct from assignment
- segment findings appear in report

### 6.3 Demo C — email

Scenario:

- create an email job
- register many variants
- simulate tranche sends
- ingest opens, clicks, conversions, unsubscribes, complaints
- reallocate between tranches
- generate report

Pass criteria:

- tranche-to-tranche reallocation works
- delayed outcomes are handled
- guardrail status is visible
- unsubscribe or complaint guardrail can cap or pause traffic

## 7. Release 1 gate

Release 1 is complete only when all are true:

- workflow demo passes,
- web demo passes,
- email demo passes,
- embedded mode works,
- service mode works,
- SQLite backend works,
- Postgres backend works,
- CLI works,
- Python SDK works,
- TypeScript SDK works,
- JSON reports work,
- Markdown or HTML reports work,
- pause, resume, and rollback work,
- adaptive policies shift traffic in at least one demo,
- docs and runbooks are sufficient for another agent to operate the system.

## 8. Contextual-ready gate

Before contextual policy work starts, the repo must additionally pass:

- context schema validation tests,
- decision envelope completeness tests,
- replay export tests,
- shadow mode scaffold tests.

## 9. No-merge rules

OpenClaw must not mark a major task complete if:

- required tests for that task were not added,
- demo flow regressed,
- an API contract changed without doc updates,
- a new architecture dependency was introduced without an ADR,
- an interface seam was removed for convenience.

## 10. Suggested fixture datasets

Include fixture data for:

- binary conversion job,
- numeric reward workflow job,
- email campaign with delayed outcomes,
- segment-aware web job.

These fixtures should be small enough to run in CI and rich enough to catch joins, windows, and guardrails.

## 11. Acceptance artifact expectations

For each major phase, produce:

- a passing demo command,
- a short sample report,
- a short execution transcript or log,
- and updated docs.

These artifacts are part of the release story, not optional extras.
