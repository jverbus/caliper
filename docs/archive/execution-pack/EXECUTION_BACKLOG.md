# Execution Backlog

This is the ordered task list OpenClaw should execute. Work top to bottom unless a task explicitly allows parallelism.

Each task includes:

- dependencies,
- core deliverables,
- acceptance criteria.

Do not mark a task complete until acceptance passes.

## Phase 0 — Foundations

### P0-001 Repo scaffold

**Depends on:** none

**Deliverables**
- top-level repo layout from `REPO_BOOTSTRAP_SPEC.md`
- placeholder packages and apps
- imported execution docs under `docs/execution/`

**Acceptance**
- directory tree matches the spec
- repo is clean and buildable
- placeholders import without runtime errors

### P0-002 Toolchain and CI

**Depends on:** P0-001

**Deliverables**
- `uv` Python workspace
- `pnpm` TypeScript workspace
- lint, type-check, test commands
- CI workflow for lint, type-check, tests

**Acceptance**
- `make setup`, `make lint`, `make typecheck`, and `make test` exist
- CI runs successfully on a clean checkout

### P0-003 ADR and governance scaffolding

**Depends on:** P0-001

**Deliverables**
- `docs/adr/`
- ADR template
- PR or change template
- work log template or equivalent

**Acceptance**
- docs exist
- `AGENT_OPERATING_MANUAL.md` process can be followed in-repo

### P0-004 Config system and profiles

**Depends on:** P0-002

**Deliverables**
- config loader
- embedded, service, shared profiles
- example env files
- basic secrets handling

**Acceptance**
- profile switch changes the selected backend config cleanly
- config tests pass

## Phase 1 — Core substrate

### P1-001 Domain models and schemas

**Depends on:** P0-004

**Deliverables**
- job, arm, policy, decision, exposure, outcome, guardrail event models
- request and response schemas
- shared schema package

**Acceptance**
- models validate correctly
- OpenAPI or JSON Schema generation works
- tests cover required fields and enums

### P1-002 Storage interfaces and SQLite backend

**Depends on:** P1-001

**Deliverables**
- repository interfaces
- SQLite implementations
- migrations or schema initialization
- basic persistence tests

**Acceptance**
- job, arm, decision, exposure, outcome persistence works on SQLite
- integration tests pass

### P1-003 Postgres backend

**Depends on:** P1-002

**Deliverables**
- Postgres implementations
- migration support
- Docker Compose service profile

**Acceptance**
- same repository tests pass on Postgres
- service mode can start against Postgres

### P1-004 Event ledger and event bus

**Depends on:** P1-002

**Deliverables**
- append-only event table
- event envelope model
- inline or DB-backed event bus abstraction
- projection hooks

**Acceptance**
- events are append-only
- duplicate handling is safe
- replay by job and window works

### P1-005 Projection rebuild support

**Depends on:** P1-004

**Deliverables**
- projection rebuild runner
- aggregate tables or views
- audit projection

**Acceptance**
- projections can be rebuilt from stored events
- report fixtures remain consistent after rebuild

## Phase 2 — Control plane

### P2-001 API app skeleton

**Depends on:** P1-003, P1-004

**Deliverables**
- FastAPI app
- dependency wiring
- health endpoints
- basic auth scaffold for shared mode

**Acceptance**
- local API starts
- health checks pass
- test client works

### P2-002 Job CRUD

**Depends on:** P2-001, P1-001

**Deliverables**
- create, read, update job endpoints
- objective, guardrail, policy, and schedule spec persistence

**Acceptance**
- job API contract matches spec
- audit records created on writes

### P2-003 Arm bulk registration and lifecycle

**Depends on:** P2-002

**Deliverables**
- batch register arms endpoint
- hold, retire, resume behavior
- arm constraints and metadata persistence

**Acceptance**
- a job can hold at least 100 arms
- state changes are auditable

### P2-004 Job state machine and approvals

**Depends on:** P2-002

**Deliverables**
- job states
- activation, pause, resume, archive flows
- approval state support

**Acceptance**
- invalid transitions are rejected
- pause is non-destructive
- audit trail is queryable

## Phase 3 — Decision loop

### P3-001 Assignment engine interface and fixed split policy

**Depends on:** P1-001, P1-004, P2-003

**Deliverables**
- assignment engine
- policy selection logic
- fixed split implementation
- decision result model

**Acceptance**
- fixed split respects weights
- decision contains propensity and diagnostics

### P3-002 Assign endpoint and idempotency

**Depends on:** P3-001, P2-001

**Deliverables**
- `POST /v1/assign`
- idempotency key persistence
- fallback handling

**Acceptance**
- retries are stable
- candidate-arm subsets are respected
- `decision.assigned` is persisted

### P3-003 Exposure ingest

**Depends on:** P3-002

**Deliverables**
- `POST /v1/exposures`
- exposure storage
- event emission
- join tests

**Acceptance**
- exposure is stored separately from decision
- duplicate exposure handling is safe

### P3-004 Outcome ingest

**Depends on:** P3-002

**Deliverables**
- `POST /v1/outcomes`
- support for multiple outcome events
- attribution windows
- cost and latency support

**Acceptance**
- delayed outcomes join correctly
- numeric and binary outcomes are supported

### P3-005 Reward engine

**Depends on:** P3-004, P2-002

**Deliverables**
- reward formula parser or evaluator
- penalty application
- normalized policy-update dataset builder

**Acceptance**
- reward values are reproducible from fixtures
- penalties and costs affect updates correctly

### P3-006 Report generation

**Depends on:** P3-005, P1-005

**Deliverables**
- JSON report output
- Markdown or HTML human-readable report
- latest report retrieval API

**Acceptance**
- report contains leaders, traffic shifts, guardrails, segment findings, recommendations
- report fixtures are deterministic

### P3-007 Worker or scheduler loop

**Depends on:** P3-006, P1-004

**Deliverables**
- periodic report trigger
- periodic policy update trigger
- due-task execution loop

**Acceptance**
- scheduled reports and updates run in tests
- pending tasks survive process restart where designed

## Phase 4 — Adaptive policies

### P4-001 Epsilon-greedy

**Depends on:** P3-005

**Deliverables**
- epsilon-greedy policy
- tests and simulations

**Acceptance**
- policy prefers better arms in seeded simulation
- propensity is valid

### P4-002 UCB1

**Depends on:** P3-005

**Deliverables**
- UCB1 policy
- tests and simulations

**Acceptance**
- policy prefers better arms in seeded simulation
- cold start is handled

### P4-003 Thompson sampling

**Depends on:** P3-005

**Deliverables**
- Bernoulli Thompson sampling
- tests and simulations

**Acceptance**
- policy shifts traffic toward better arms in seeded simulation
- diagnostics are present

### P4-004 Policy snapshot versioning

**Depends on:** P4-001, P4-002, P4-003, P3-007

**Deliverables**
- immutable snapshot storage
- activation and rollback flow
- `policy.updated` event

**Acceptance**
- assignment uses active snapshot only
- rollback to prior snapshot works

### P4-005 Guardrail engine and auto actions

**Depends on:** P3-005, P3-007

**Deliverables**
- guardrail evaluator
- cap, pause, or demote actions
- guardrail events in reports

**Acceptance**
- fixture breach caps or pauses as configured
- report and audit surfaces show the action

## Phase 5 — Workflow surface

### P5-001 CLI

**Depends on:** P2-003, P3-006

**Deliverables**
- CLI commands for create job, add arms, assign, log exposure, log outcome, generate report, pause, resume

**Acceptance**
- major core flows can be run without raw HTTP
- help text is present

### P5-002 Python SDK

**Depends on:** P2-003, P3-006

**Deliverables**
- service client
- embedded client
- shared schema use
- examples

**Acceptance**
- embedded and service flows both work in tests
- SDK mirrors API operations

### P5-003 Workflow adapter

**Depends on:** P5-002, P4-003

**Deliverables**
- workflow adapter API
- sample workflow execution hooks
- latency and cost logging
- optional human acceptance outcome example

**Acceptance**
- workflow demo runs end to end
- traffic adapts in simulation or demo

### P5-004 Workflow demo and docs

**Depends on:** P5-003, P5-001

**Deliverables**
- `examples/workflow_demo`
- `make demo-workflow`
- sample reports checked into docs or fixtures

**Acceptance**
- demo passes in embedded mode
- demo passes in service mode

## Phase 6 — Web surface

### P6-001 TypeScript SDK

**Depends on:** P2-003, P3-006

**Deliverables**
- TS client for job, arm, assign, exposure, outcome, reports
- typed contracts
- build and publish scripts or local pack flow

**Acceptance**
- TS SDK compiles
- integration tests can call live API

### P6-002 Web adapter

**Depends on:** P6-001, P3-002, P3-003

**Deliverables**
- request-time assignment helper
- exposure logging helper
- click and conversion logging helper

**Acceptance**
- adapter works in a reference app
- actual render logging is distinct from assignment

### P6-003 Web demo

**Depends on:** P6-002, P4-003

**Deliverables**
- `examples/web_demo`
- `make demo-web`
- segment-aware report example

**Acceptance**
- demo shows request-time assignment
- report shows segment findings

## Phase 7 — Email surface

### P7-001 Email adapter core

**Depends on:** P5-002, P4-003

**Deliverables**
- recipient import or recipient-ID ingestion
- assignment for send tranche
- send-plan representation
- handoff to simulator or pluggable ESP

**Acceptance**
- tranche assignments can be generated deterministically
- adapter preserves decision IDs

### P7-002 Email webhook and outcome ingest

**Depends on:** P7-001, P3-004

**Deliverables**
- open, click, conversion, unsubscribe, complaint mapping
- delayed outcome support
- idempotent webhook handling

**Acceptance**
- webhook duplicates are safe
- guardrail metrics can be derived

### P7-003 Tranche reallocation

**Depends on:** P7-002, P3-007, P4-003

**Deliverables**
- tranche planner update loop
- policy update between tranches
- traffic caps on offending arms

**Acceptance**
- later tranches use updated allocation
- guardrail breach can cap or pause

### P7-004 Email demo

**Depends on:** P7-003, P5-001

**Deliverables**
- `examples/email_demo`
- `make demo-email`
- sample email campaign report

**Acceptance**
- demo runs end to end
- report includes guardrail behavior and delayed outcomes

## Phase 8 — Hardening

### P8-001 Human-readable reports polish

**Depends on:** P3-006

**Deliverables**
- stable Markdown report format
- HTML report renderer
- recommendation language rules

**Acceptance**
- reports are understandable without a UI
- sample outputs are checked in

### P8-002 Pause, promote, and rollback UX

**Depends on:** P4-004, P4-005, P5-001

**Deliverables**
- CLI and API flows for pause, resume, and rollback
- audit visibility for those actions

**Acceptance**
- operator can confidently stop or revert a job
- tests cover rollback correctness

### P8-003 Packaging and install flow

**Depends on:** P5-004, P6-003, P7-004

**Deliverables**
- install instructions
- local data directory setup
- seeded demo data
- service-mode compose flow

**Acceptance**
- another machine can install and run the demos from docs alone

### P8-004 Backup and restore runbook verification

**Depends on:** P8-003

**Deliverables**
- export and restore scripts or documented commands
- runbook walkthrough
- smoke test for restore

**Acceptance**
- data and reports can be recovered in a simple local scenario

## Phase 9 — Contextual-ready

### P9-001 Context schema versioning

**Depends on:** P3-002

**Deliverables**
- `context_schema_version`
- context validation and redaction hooks
- context storage policy

**Acceptance**
- decision envelope supports versioned context
- tests cover missing and disallowed fields

### P9-002 Shadow mode scaffold

**Depends on:** P4-004, P9-001

**Deliverables**
- shadow job or policy state
- parallel decision evaluation hooks without live routing impact

**Acceptance**
- shadow evaluations do not affect active routing
- audit trail is preserved

### P9-003 Replay export and OPE scaffold

**Depends on:** P9-001, P1-004

**Deliverables**
- replay dataset export format
- `py-caliper-ope` scaffold
- basic dataset integrity tests

**Acceptance**
- exports contain context, chosen action, propensity, reward, and timestamps

### P9-004 Contextual promotion gate scaffold

**Depends on:** P9-002, P9-003

**Deliverables**
- non-live gate checks for future contextual policies
- policy state rules preventing accidental activation

**Acceptance**
- contextual runtime cannot be enabled without gate checks

## Post-v1 backlog

Do not execute until the release-1 gate passes.

- PV1-001 disjoint LinUCB
- PV1-002 VW policy backend
- PV1-003 OBP integration
- PV1-004 organization router runtime
- PV1-005 Kafka event bus
- PV1-006 ClickHouse analytics backend
- PV1-007 Temporal scheduler backend
- PV1-008 minimal operator UI

## Parallelism rules

Safe parallelism is allowed only when dependencies are satisfied, for example:

- P1-003 can proceed after P1-002 while P1-004 is underway
- P6-001 can proceed while P5 workflow demo docs are being polished
- P8 documentation and packaging work can overlap after demos are stable

Never parallelize in ways that compromise the frozen phase gates.
