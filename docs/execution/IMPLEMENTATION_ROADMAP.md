# Implementation Roadmap

This roadmap translates the build charter into a sequence of executable phases. Each phase ends with a black-box acceptance gate.

## Phase summary

| Phase | Name | Goal |
|---|---|---|
| 0 | Foundations | Create a repo and toolchain that can be built, tested, and run locally |
| 1 | Core substrate | Define domain model, storage, events, and configuration profiles |
| 2 | Control plane | Create jobs, arms, and lifecycle management |
| 3 | Decision loop | Assignment, exposure, outcome, reward, reports |
| 4 | Adaptive policies | Add simple bandits, guardrails, policy snapshots |
| 5 | Workflow surface | Prove end-to-end execution in embedded and service modes |
| 6 | Web surface | Add remote or hosted web assignment and tracking |
| 7 | Email surface | Add tranche-based email optimization and outcome ingestion |
| 8 | Hardening | Reports, governance, packaging, runbook, reproducibility |
| 9 | Contextual-ready | Add schema hooks, shadow mode, replay exports, OPE scaffold |
| 10 | Post-v1 | Contextual runtime, VW, org routing, scale stack |

## Phase 0 — Foundations

### Goal
Create the repo, toolchain, commands, and docs structure so OpenClaw can work safely and repeatedly.

### Deliverables
- monorepo scaffold
- Python workspace
- TypeScript workspace
- lint, type-check, and test commands
- CI workflow
- docs import under `docs/execution/`
- ADR directory
- deployment profile config skeleton
- Docker Compose for service-mode dependencies

### Exit gate
A fresh clone can:

- install dependencies,
- run lint,
- run tests,
- start an embedded hello-world runtime,
- start a local API service.

## Phase 1 — Core substrate

### Goal
Create the shared runtime substrate independent of any surface.

### Deliverables
- domain models
- schema definitions
- storage interfaces
- SQLite backend
- PostgreSQL backend
- append-only event ledger
- event bus abstraction
- config system
- migration system

### Exit gate
An integration test can create a job, persist it, append events, and rebuild projections from stored state.

## Phase 2 — Control plane

### Goal
Let a user or SDK define optimization jobs and manage arms safely.

### Deliverables
- job CRUD
- arm bulk registration
- arm state transitions
- job state machine
- audit log endpoints
- approval state storage
- policy spec persistence
- segment spec persistence

### Exit gate
A black-box test can create a job, add arms, pause it, resume it, and read an audit trail.

## Phase 3 — Decision loop

### Goal
Make one complete loop work from decision to report.

### Deliverables
- assignment engine interface
- fixed split policy
- `/assign` endpoint
- exposure ingest
- outcome ingest
- delayed attribution handling
- reward engine
- report generation
- worker or scheduler loop

### Exit gate
A demo can create a job, assign real opportunities, ingest exposures and outcomes, and emit a report with leaders and metrics.

## Phase 4 — Adaptive policies

### Goal
Turn the static loop into an adaptive one.

### Deliverables
- epsilon-greedy
- UCB1
- Thompson sampling
- policy snapshots and versioning
- update cadence controller
- guardrail evaluation
- auto-cap and auto-pause
- decision diagnostics

### Exit gate
A simulation or live demo shows traffic shifting toward better-performing arms while respecting guardrails.

## Phase 5 — Workflow surface

### Goal
Prove that Caliper works in the most flexible and lowest-friction environment first.

### Deliverables
- Python SDK
- CLI
- workflow adapter
- embedded runtime API
- service-mode workflow example
- human acceptance or quality outcome example

### Exit gate
`make demo-workflow` runs end to end in both embedded mode and service mode.

## Phase 6 — Web surface

### Goal
Support a real web or landing-page use case.

### Deliverables
- TypeScript SDK
- web adapter
- request-time assignment flow
- exposure logging for actual renders
- click and conversion logging
- reference web demo

### Exit gate
`make demo-web` serves or simulates real web requests and produces a report showing arm-level performance and traffic shifts.

## Phase 7 — Email surface

### Goal
Support the user's tranche-based email optimization use case.

### Deliverables
- pre-send assignment API usage pattern
- batch or tranche planner
- open, click, conversion, unsubscribe, complaint ingest
- delayed attribution windows
- bandit reallocation across tranches
- reference email demo or simulator

### Exit gate
`make demo-email` sends or simulates multiple tranches, adapts traffic between them, and produces a report with guardrail behavior.

## Phase 8 — Hardening

### Goal
Make the product trustworthy to operate and easy for another agent to run.

### Deliverables
- JSON report schema
- Markdown and HTML report renderers
- rollback flows
- reproducibility tests
- backup and restore runbook
- package and install documentation
- seeded demo data
- polished CLI flows

### Exit gate
Another operator or agent can clone the repo, run the demos, and understand the output from docs and runbooks alone.

## Phase 9 — Contextual-ready

### Goal
Add the minimum substrate needed for future contextual policies without taking on contextual runtime complexity yet.

### Deliverables
- `context_schema_version`
- context validation
- candidate arms per request
- valid propensity enforcement
- replay export format
- shadow policy state
- `py-caliper-ope` scaffold
- contextual promotion gate scaffold

### Exit gate
The platform can export replay datasets with valid decision metadata and run a non-live shadow flow.

## Phase 10 — Post-v1 roadmap

These items are explicitly after v1:

- disjoint LinUCB
- richer contextual diagnostics
- VW backend
- OBP integration
- org-router runtime
- child-policy routing
- ClickHouse analytics backend
- Kafka or Redpanda event bus
- Temporal scheduler backend
- operator UI

## Sequencing rules

1. Do not start a later phase before the current exit gate passes.
2. Prefer vertical slices over infrastructure-first expansion.
3. Avoid adding scale infrastructure until current performance evidence justifies it.
4. Workflow comes before web, and web comes before email, but email is still part of v1.
5. Contextual-ready scaffolding belongs after the core non-contextual product is trustworthy.

## Recommended first 12 PRs

1. repo scaffold and toolchain
2. config system and deployment profiles
3. domain models and schemas
4. storage interfaces and SQLite backend
5. Postgres backend and migrations
6. event ledger and projections
7. control-plane job and arm CRUD
8. fixed-split assignment API
9. exposure and outcome ingest
10. reward engine and report generation
11. epsilon-greedy, UCB1, and Thompson sampling
12. Python SDK, CLI, and workflow demo

## Why this order is frozen

This sequence gets to a working product quickly while preserving the broad platform shape:

- build the substrate once,
- prove the loop on a workflow,
- then extend to web and email,
- then harden,
- then add contextual-ready hooks.

That is the shortest path to a real, usable Caliper.
