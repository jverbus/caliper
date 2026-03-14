# Repo Bootstrap Spec

This spec defines the initial repository layout, toolchain, commands, and deployment profiles for the new Caliper repo.

## 1. Repo goals

The repo must be:

- easy to clone,
- easy to run on one machine,
- easy to promote to a shared service,
- and modular enough to upgrade infrastructure later.

The initial repo must optimize for developer and agent autonomy, not platform sprawl.

## 2. Top-level layout

```text
caliper/
  apps/
    api/                       # FastAPI control plane, assign, ingest
    worker/                    # report generation and policy updates
    cli/                       # Typer CLI

  packages/
    py-caliper-core/           # domain models, interfaces, config, errors
    py-caliper-storage/        # repositories, SQLite and Postgres backends
    py-caliper-events/         # event ledger, event bus, projections
    py-caliper-policies/       # fixed split, epsilon, UCB1, Thompson
    py-caliper-reward/         # objectives, penalties, guardrails
    py-caliper-reports/        # JSON, Markdown, HTML reports
    py-caliper-adapters/       # workflow, web, email adapter code
    py-caliper-ope/            # replay and OPE scaffold, v1.5+
    py-sdk/                    # Python SDK
    ts-sdk/                    # TypeScript SDK
    schemas/                   # JSON Schema / OpenAPI contracts

  examples/
    workflow_demo/
    web_demo/
    email_demo/

  deploy/
    compose/
    docker/

  docs/
    execution/
    adr/
    runbooks/

  tests/
    unit/
    integration/
    property/
    replay/
    load/

  scripts/
  data/                        # local dev data, gitignored
  reports/                     # generated reports, gitignored
  Makefile
  pyproject.toml
  pnpm-workspace.yaml
  package.json
  README.md
```

## 3. Why this layout

- `apps/` contains runnables.
- `packages/` contains reusable domain and runtime logic.
- `examples/` is mandatory because Caliper must prove real-world surfaces.
- `docs/execution/` keeps this pack in-repo so OpenClaw can always refer to it.
- `tests/` mirrors the acceptance strategy.
- `deploy/` enables local and shared-service operation without forcing heavy infra.

## 4. Toolchain

### Python

- Python 3.12+
- `uv` for workspace and dependency management
- `ruff` for lint and formatting
- `mypy` for type checking
- `pytest` for tests
- `hypothesis` for property tests
- `httpx` for API client tests
- `SQLAlchemy` + Alembic for persistence
- `Pydantic v2` for runtime schemas
- `Typer` for CLI
- `structlog` or stdlib structured logging

### TypeScript

- Node 20+
- `pnpm`
- TypeScript
- `tsup` or equivalent for SDK builds
- no required frontend UI package in v1

## 5. Mandatory root commands

The repo must provide these commands, whether via `make`, `just`, or scripts:

- `make setup`
- `make lint`
- `make format`
- `make typecheck`
- `make test`
- `make test-unit`
- `make test-integration`
- `make test-property`
- `make demo-workflow`
- `make demo-web`
- `make demo-email`
- `make run-embedded`
- `make run-service`
- `make run-worker`
- `make seed-demo-data`

These commands are part of the acceptance surface and must remain stable.

## 6. Deployment profiles

The config layer must support these profiles with the same domain model.

### 6.1 Embedded profile

Recommended defaults:

- `CALIPER_PROFILE=embedded`
- `CALIPER_DB_URL=sqlite:///./data/caliper.db`
- local artifact directory for reports and exports
- no external services required

### 6.2 Service profile

Recommended defaults:

- `CALIPER_PROFILE=service`
- `CALIPER_DB_URL=postgresql+psycopg://...`
- separate API and worker processes
- same core runtime as embedded profile

### 6.3 Shared-service profile

Recommended defaults:

- `CALIPER_PROFILE=shared`
- same service stack as service profile
- API-key or bearer-token auth
- configurable base URL for SDKs and adapters

## 7. Local infrastructure expectations

### 7.1 Mandatory in v1

- none for embedded mode beyond Python
- PostgreSQL container or local Postgres for service mode

### 7.2 Optional in v1

- Docker Compose for service-mode boot
- optional reverse proxy
- optional SMTP or ESP simulator for email examples

### 7.3 Explicitly not required in v1

- Redis
- Kafka
- ClickHouse
- Temporal
- Kubernetes

## 8. CI expectations

CI must run at least:

- lint
- type-check
- unit tests
- integration tests against SQLite
- service-profile smoke test against Postgres
- SDK contract generation check

One CI job should also verify that the demo commands at least start or run in a smoke-test mode.

## 9. Package ownership rules

- `py-caliper-core` must have no app dependencies.
- `py-caliper-storage` depends on core only.
- `py-caliper-events` depends on core and storage interfaces only.
- `py-caliper-policies` depends on core interfaces only.
- `py-caliper-reward` depends on core interfaces only.
- adapters depend on core plus SDK contracts, not on app internals.
- apps wire packages together but do not define the domain.
- SDKs must use shared schemas or generated contracts, not duplicate them manually.

## 10. Schema discipline

Maintain one source of truth for external contracts.

Required artifacts:

- Pydantic models for runtime
- OpenAPI spec for HTTP surface
- JSON Schemas for SDK generation where useful

## 11. Logging and observability

V1 must include:

- structured logs,
- request IDs,
- decision IDs in logs,
- policy version in assignment logs,
- report generation logs,
- guardrail event logs.

Nice-to-have later:

- metrics endpoint,
- traces,
- OpenTelemetry.

## 12. Security baseline

V1 must support:

- API-key or bearer auth in shared-service mode,
- per-workspace resource scoping,
- redaction or exclusion of sensitive fields from context logging,
- retention settings in config.

## 13. First bootstrap checklist

The first repo bootstrap PR should include:

- directory skeleton,
- Python workspace,
- TypeScript workspace,
- root task runner,
- placeholder app entrypoints,
- config loader,
- CI config,
- docs import,
- ADR folder,
- basic README,
- smoke tests.

Do not begin real domain work before this checklist passes.
