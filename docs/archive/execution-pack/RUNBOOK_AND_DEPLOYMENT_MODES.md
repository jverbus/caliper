# Runbook and Deployment Modes

This document explains how Caliper should be operated in v1.

## 1. Purpose

Caliper must be easy to run:

- on the same box as OpenClaw,
- as a small local service,
- or as a shared service on a server.

The operator should not need a heavyweight platform to get value.

## 2. Deployment modes

## 2.1 Embedded mode

Best for:

- local workflows,
- prompt and tool-chain optimization,
- developer testing,
- lightweight same-box usage.

Characteristics:

- no required HTTP hop,
- SQLite by default,
- local filesystem artifacts,
- can still emit reports and schedule updates.

Suggested startup goal:

- one command or one Python entrypoint that initializes the runtime and runs a demo.

## 2.2 Service mode

Best for:

- local machine plus browser, site, or webhook integrations,
- remote clients on the same network,
- cleaner process separation between API and worker.

Characteristics:

- FastAPI app,
- Postgres backend,
- separate worker process,
- same domain logic as embedded mode.

Suggested startup goal:

- one compose command or one make command to start API, worker, and Postgres.

## 2.3 Shared-service mode

Best for:

- hosted sites,
- hosted workflows,
- remote email integrations,
- multi-workspace usage.

Characteristics:

- same service runtime,
- auth enabled,
- stable base URL,
- workspace scoping.

## 3. Connectivity patterns

### 3.1 Same-box workflow

Use embedded runtime or Python SDK.

### 3.2 Site or service on another machine

Use shared-service mode.

### 3.3 Hosted site calling a local Caliper instance

Only valid if the local Caliper service is reachable by the site. If not, use shared-service mode or colocate Caliper.

## 4. Minimal operational commands

The repo should eventually support commands equivalent to:

```bash
make setup
make run-embedded
make run-service
make run-worker
make demo-workflow
make demo-web
make demo-email
```

## 5. Data locations

Recommended defaults:

- `./data/` for SQLite and local state in embedded mode
- `./reports/` for generated reports
- `./exports/` for replay or dataset exports
- Postgres database for service and shared-service modes

Keep these configurable.

## 6. Backup and restore

V1 only needs pragmatic backup guidance.

Embedded mode:

- stop the process if needed,
- copy the SQLite database file and report/export directories,
- document restore steps.

Service mode:

- use Postgres dump or equivalent,
- preserve report and export directories,
- document restore steps.

## 7. Scheduling

V1 scheduling is handled by the worker loop.

Required scheduled behaviors:

- policy update jobs,
- report generation jobs,
- startup recovery of due tasks where supported.

No Temporal requirement in v1.

## 8. Report operation

Every active job should be able to:

- generate a report on demand,
- generate a scheduled morning report,
- store the report in JSON and Markdown or HTML form,
- retrieve the latest report through API or CLI.

## 9. Guardrail operation

Operators must be able to:

- inspect current guardrail status,
- see which arm or job triggered a breach,
- understand what automatic action was taken,
- resume a job after manual review if allowed.

## 10. Observability basics

V1 should expose enough logs to answer:

- what decision was made,
- what policy version made it,
- whether exposure happened,
- whether outcomes arrived,
- what report was generated,
- whether any guardrails fired.

## 11. When to adopt heavier infrastructure

Only consider Kafka, ClickHouse, Redis, or Temporal after evidence shows one of these is true:

- service-mode assignment traffic is high enough that DB-backed eventing is the bottleneck,
- report or aggregate queries are too slow on the chosen SQL backend,
- scheduling complexity exceeds the DB-backed worker design,
- multiple adapters and workloads need stronger decoupling.

Until then, keep the v1 runbook simple.

## 12. Operator checklist

Before running a real job:

- confirm the correct profile is selected,
- confirm the DB path or connection string,
- confirm workspace auth where relevant,
- confirm report and export directories,
- confirm guardrail thresholds,
- confirm policy update cadence,
- confirm the adapter can log exposure and outcomes.

## 13. Release handoff checklist

Before declaring the repo ready to share with another agent:

- docs are present in `docs/execution/`,
- runbook matches actual commands,
- demo commands work,
- sample reports exist,
- backup and restore guidance was tested,
- service and embedded modes both work.
