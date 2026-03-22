# Build Charter

This document freezes the implementation target for the first build of Caliper.

It converts the broader PRD and RFC into a concrete v1 contract that an autonomous builder can execute without inventing scope.

## 1. Product mission

Caliper is the adaptive decision and measurement layer for autonomous work.

Its job is to let an operator or agent say:

- create many variants,
- serve or route them,
- measure what works,
- shift traffic safely,
- and report back with trustworthy findings.

The product is intentionally broader than AI evals. Its core primitives must support:

- artifacts such as websites, landing pages, copy, and emails,
- workflows such as prompt chains and tool sequences,
- and future organizations or clusters as arms.

## 2. Frozen v1 outcome

The build is considered successful when a user or agent can:

1. create an optimization job,
2. register many arms,
3. define objective and guardrails,
4. choose a simple adaptive policy,
5. launch on a live surface,
6. ingest exposures and outcomes,
7. see traffic shifts and why they happened,
8. receive a morning report in machine-readable and human-readable form,
9. pause, promote, or rollback safely,
10. run Caliper embedded on one machine or as a small shared service.

## 3. Frozen v1 scope

The following are in scope for v1:

- optimization jobs,
- arm lifecycle management,
- policy versioning,
- fixed split,
- epsilon-greedy,
- UCB1,
- Thompson sampling,
- per-request candidate arm lists,
- exposure and outcome ingestion,
- delayed attribution windows,
- reward formulas,
- hard guardrails and penalties,
- audit logs,
- pause, resume, and rollback,
- machine-readable reports,
- human-readable reports,
- Python SDK,
- TypeScript SDK,
- workflow adapter,
- web adapter,
- email adapter,
- segment-aware analysis,
- contextual-ready logging and schema hooks.

## 4. Explicitly out of v1 critical path

The following are not allowed to delay v1:

- browser UI or dashboard,
- ClickHouse,
- Kafka or Redpanda,
- Redis,
- Temporal,
- Vowpal Wabbit runtime integration,
- OBP-based OPE runtime integration,
- generalized hierarchical routing,
- full org-router runtime,
- feature store infrastructure,
- full warehouse-native analytics,
- deep RL,
- creative generation inside Caliper.

Some of these may appear as empty interface seams, optional extras, or scaffolds. They must not become build blockers.

## 5. v1 deployment modes

Caliper must support the same core domain and APIs across three modes.

### 5.1 Embedded mode

Default and mandatory for v1.

- Runs on the same machine as OpenClaw.
- Can be imported as a Python library and called in-process.
- Uses local disk and SQLite by default.
- Suitable for workflow optimization, local experimentation, and moderate traffic.

### 5.2 Local service mode

Mandatory for v1.

- Runs as a small API service on the local machine or a nearby box.
- Uses FastAPI and a SQL backend.
- Can be called by local tools, scripts, websites, or ESP/webhook integrations.
- Shared configuration and domain logic must be the same as embedded mode.

### 5.3 Shared service mode

Mandatory for v1.

- Same logical service as local service mode, but accessible by remote clients.
- Supports API-key based auth per workspace.
- Suitable when the optimized site or workflow is not colocated with OpenClaw.

### 5.4 Future scale mode

Not required in v1, but architecture must leave room for:

- Kafka or Redpanda,
- ClickHouse,
- Redis,
- Temporal,
- object storage,
- Vowpal Wabbit,
- richer policy backends,
- multi-level routing.

## 6. Technology freeze for v1

### 6.1 Required stack

- Python 3.12+
- `uv` for Python workspace and package management
- FastAPI for HTTP APIs
- SQLAlchemy + Alembic for persistence
- Pydantic v2 for runtime schemas
- `pytest` + `hypothesis` for tests
- `ruff` + `mypy` for quality
- Typer for CLI
- `pnpm` for TypeScript workspace
- a TypeScript SDK package
- Markdown, JSON, and HTML reports

### 6.2 Default persistence choices

- SQLite in embedded mode
- PostgreSQL in service and shared-service mode
- local filesystem for report and export artifacts
- no mandatory external queue or cache in v1

### 6.3 Explicit v1 overrides to the broad RFC

The reference RFC names a heavier default stack. For this implementation charter, that is downgraded to future-scale status.

The actual v1 build must be:

- lighter,
- easier to clone and boot,
- operable with minimal local infrastructure,
- and ready to upgrade later through explicit interfaces.

## 7. Architecture principles

1. **Control plane is product IP**
   - Job creation, arm lifecycle, assignments, outcomes, reports, and governance must be Caliper-native.

2. **Events are append-only**
   - Mutable state should be derived from persisted events and metadata, not vice versa.

3. **Every decision is auditable**
   - A decision must be reconstructible from job, arm, policy version, context schema version, propensity, and timestamps.

4. **Interfaces before scale**
   - Build abstractions for storage, eventing, scheduling, and policy backends now.
   - Implement the simplest backend first.

5. **Embedded and service modes share one core runtime**
   - Avoid forking business logic by transport or deployment mode.

6. **UI is optional**
   - Reports and CLI are enough to operate v1.

7. **Contextual-ready before contextual**
   - The platform must log and validate everything needed for future contextual policy evaluation before it runs one.

8. **Broad surface semantics**
   - The domain model must not hardcode “web page test” assumptions.

## 8. Required interface seams

The v1 codebase must expose interfaces for:

- state storage,
- event ledger and event bus,
- policy backend,
- assignment engine,
- reward engine,
- scheduler,
- report renderer,
- adapter contract,
- identity and idempotency,
- artifact storage or payload resolution.

The first implementation can be simple. The interface must not be skipped.

## 9. Product boundary decisions

### 9.1 What Caliper owns

- optimization job definitions,
- arms and arm lifecycle,
- decisioning,
- propensities,
- objectives and guardrails,
- event logging,
- bandit updates,
- reports,
- governance,
- SDKs and adapter contracts.

### 9.2 What Caliper does not replace in v1

- CMS,
- ESP,
- website hosting platform,
- full workflow engine,
- agent builder platform,
- feature store,
- enterprise BI stack.

Caliper integrates with those systems rather than replacing them.

## 10. Surface priority

The runtime and domain model must support all first-class surfaces from day one, but implementation order is frozen:

1. workflow adapter first,
2. web adapter second,
3. email adapter third,
4. org-router semantics as schema only in v1, runtime later.

This order optimizes for fast end-to-end wins while preserving breadth.

## 11. Reporting contract

Every active job must be able to emit:

- JSON report for agents,
- Markdown or HTML report for humans,
- clear statement of leaders, traffic shifts, uncertainty, segment findings, guardrails, and recommendations.

PDF export is optional later.

## 12. Governance contract

Jobs must support at least these states:

- `draft`
- `shadow`
- `active`
- `paused`
- `completed`
- `archived`

Policies must be versioned. Policy and job changes must be auditable.

## 13. Segment-aware requirement

V1 does not require contextual policies, but it does require segment-aware analysis.

That means the platform must support:

- versioned context or metadata fields,
- report grouping by configured segments,
- candidate arms per request,
- persisted decision metadata needed for later replay.

## 14. Explicit post-v1 items

These are real roadmap items, not current acceptance criteria:

- disjoint LinUCB,
- VW backend,
- OBP workflows,
- shadow-to-active contextual promotion gates,
- hierarchical routing runtime,
- org-router runtime,
- high-throughput event streaming,
- dedicated analytics store,
- browser UI.

## 15. Decision rule

If an implementation choice makes v1 heavier, slower to boot, or more operationally complex without being required by the frozen acceptance gates, do not take that path.

Choose the simplest implementation that:

- preserves interfaces,
- passes acceptance,
- and leaves clear upgrade seams.

## 16. Final v1 release gate

Caliper v1 ships only when all of the following are true:

- embedded mode works,
- local or shared service mode works,
- the core decision loop works,
- simple bandits shift traffic,
- reports are trustworthy and reproducible,
- pause and rollback work,
- workflow, web, and email adapters all function at MVP level,
- CLI, Python SDK, and TypeScript SDK exist,
- and the system can be installed and run by another agent from the repo with the runbook alone.
