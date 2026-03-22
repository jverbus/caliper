# Architecture Spec

This is the concrete runtime architecture for the Caliper v1 build.

It is intentionally simpler than a future scale-out platform, while preserving clear seams for later evolution.

## 1. High-level architecture

```text
SDK / CLI / Adapter
    -> Assignment API or embedded runtime
        -> Assignment Engine
            -> Policy Snapshot
            -> State Store
            -> Event Ledger
    -> Exposure / Outcome Ingest
        -> Event Ledger
        -> Projections / Aggregates
        -> Reward Engine
        -> Worker / Scheduler
            -> Policy Update
            -> Guardrail Evaluation
            -> Report Generation
```

The same core domain and logic must power all deployment modes.

## 2. Runtime modes

### 2.1 Embedded runtime

The embedded runtime is a Python object graph that exposes the same operations as the HTTP API:

- create job,
- add arms,
- assign,
- log exposure,
- log outcome,
- generate report,
- pause or resume job.

It is optimized for:

- same-box workflow use,
- local experimentation,
- agent-native execution.

### 2.2 Service runtime

The service runtime exposes the same core operations over HTTP with FastAPI.

It is optimized for:

- remote web surfaces,
- email webhook integrations,
- shared access by multiple clients.

### 2.3 Shared-service runtime

Same as service runtime, with:

- auth,
- workspace isolation,
- configurable base URLs,
- stable external contracts.

## 3. Core components

## 3.1 Control-plane API

Responsibilities:

- create and manage jobs,
- manage arms,
- manage job lifecycle state,
- store objective and guardrail specs,
- store policy specs,
- trigger and retrieve reports.

It should not own the bandit math directly. It wires domain objects and persists metadata.

## 3.2 Assignment engine

Responsibilities:

- validate the job is eligible for assignment,
- choose a candidate arm,
- return propensity and diagnostics,
- persist `decision.assigned`,
- support candidate-arm subsets,
- support fallback policy behavior.

The assignment engine must be transport-agnostic so embedded mode and service mode both use it.

## 3.3 Event ledger

Responsibilities:

- persist append-only events,
- support replay by job and time window,
- preserve raw decision envelopes,
- support idempotent writes,
- feed projection rebuilds.

Initial implementation:

- SQL-backed append-only table.

Future implementations may add:

- Kafka or Redpanda,
- ClickHouse sink,
- CDC pipelines.

## 3.4 Projections and aggregates

Responsibilities:

- rebuild job state views,
- compute per-arm metrics,
- compute segment views,
- support report generation,
- produce update-ready policy statistics.

Initial implementation:

- synchronous projection writes and SQL aggregates,
- plus worker-driven recompute where needed.

## 3.5 Reward engine

Responsibilities:

- normalize raw outcomes,
- apply formulas,
- apply penalties,
- evaluate guardrails,
- build training or update datasets for policies.

## 3.6 Worker and scheduler

Responsibilities:

- trigger periodic policy updates,
- trigger scheduled reports,
- enforce watermark or window logic for delayed outcomes,
- rebuild projections when necessary.

Initial implementation:

- DB-backed scheduler loop or APScheduler-style process.
- No Temporal in v1.

## 3.7 Report engine

Responsibilities:

- produce JSON, Markdown, and HTML reports,
- explain traffic shifts,
- show leaders and uncertainty language,
- surface guardrail events,
- generate recommendations.

## 4. Storage abstraction

Caliper must not hardwire one database path across all deployments.

Define at least these interfaces:

- `JobRepository`
- `ArmRepository`
- `DecisionRepository`
- `ExposureRepository`
- `OutcomeRepository`
- `GuardrailEventRepository`
- `PolicySnapshotRepository`
- `AuditRepository`
- `EventLedger`

Provide these initial implementations:

- SQLite repositories for embedded mode
- PostgreSQL repositories for service and shared-service modes

## 5. Eventing abstraction

Define two layers, not one:

### 5.1 Event ledger

The source of truth. Append-only persistence.

### 5.2 Event bus

A dispatch interface for projections and hooks.

Initial implementation:

- inline or DB-backed dispatch after ledger append.

Future implementation:

- Kafka or Redpanda.

This split is important because the event ledger can remain the source of truth even when the bus changes later.

## 6. Scheduler abstraction

Define a `Scheduler` or `JobRunner` interface with operations like:

- schedule report
- schedule policy update
- cancel schedule
- run due tasks
- resume pending tasks on startup

Initial implementation:

- process-local worker with DB-backed task table.

Future implementation:

- Temporal adapter.

## 7. Policy snapshot lifecycle

V1 policies must be snapshot-based.

Flow:

1. current policy version is loaded for a job,
2. assignment requests use an immutable snapshot,
3. worker computes next snapshot from outcomes,
4. snapshot is validated,
5. snapshot is activated,
6. audit event is emitted.

This is simpler and safer than mutating live policy state per request.

## 8. Assignment data flow

### 8.1 Embedded or workflow flow

```text
OpenClaw workflow
  -> Python SDK / embedded runtime
  -> assign()
  -> execute chosen arm
  -> log_exposure()
  -> log_outcome()
  -> generate_report()
```

### 8.2 Web flow

```text
web request
  -> server or middleware calls Caliper assign API
  -> chosen arm rendered
  -> exposure logged on actual render
  -> click and conversion events logged later
  -> worker updates policy and reports
```

### 8.3 Email flow

```text
campaign tranche planner
  -> assign recipients to arms
  -> send via ESP or simulator
  -> ingest opens, clicks, conversions, unsubscribes, complaints
  -> update before next tranche
  -> emit report
```

## 9. Remote site calling local Caliper

This is supported only when the local Caliper instance is network-reachable from the hosted site.

If the optimized site is remote and the local Caliper instance is not reachable, use one of these patterns:

- deploy Caliper in shared-service mode on a server,
- colocate Caliper with the site,
- or run a relay or tunnel outside the core product scope.

V1 must support the first two. It does not need to build tunneling itself.

## 10. Adapter boundary

Adapters must not embed policy logic.

Adapters are responsible for:

- opportunity capture,
- arm execution or rendering,
- identity and idempotency propagation,
- logging exposure only when the arm was truly used,
- logging outcomes with correct timestamps and windows.

The assignment engine remains the source of truth for decisions.

## 11. Multi-surface identity model

Every decision must be joinable across downstream events.

Minimum identifiers:

- `workspace_id`
- `job_id`
- `decision_id`
- `unit_id`
- adapter-specific external IDs where relevant

Examples:

- web session or visitor ID,
- email recipient ID,
- workflow task ID,
- agent request ID.

## 12. Audit model

The platform must preserve enough data to answer:

- what policy version made this decision,
- which arms were eligible,
- what propensity was logged,
- what outcome arrived later,
- why traffic shifted.

This implies:

- immutable decision records,
- immutable events,
- separate mutable projections,
- reproducible report windows.

## 13. Future seams that must exist now

The codebase must make it straightforward to add later:

- `KafkaEventBus`
- `ClickHouseAnalyticsStore`
- `TemporalScheduler`
- `VWPolicyBackend`
- `OBPReplayEvaluator`
- `OrganizationRouterBackend`

Do not implement these fully in v1. Do implement the interfaces and injection points that make them plausible upgrades.

## 14. Optional UI stance

A browser UI may be useful later, but v1 must treat it as an optional consumer of:

- report APIs,
- metrics APIs,
- audit APIs.

The architecture must not depend on a UI for correctness or operation.

## 15. Design standard

Favor a small number of components with sharp contracts over many services.

In v1, it is acceptable for `apps/api` to expose:

- control-plane endpoints,
- assignment endpoints,
- ingest endpoints,

as long as the internal modules remain separated.

Splitting into more services later is allowed. Splitting too early is not.
