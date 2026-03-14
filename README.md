# Caliper

Caliper is an adaptive decision and measurement layer for autonomous work.

This repository contains the v1 implementation scaffold and core substrate, designed to run:

- embedded (same process / same machine),
- as a local service,
- and as a shared service.

## Repository layout

- `apps/` runnable entry points (`api`, `worker`, `cli`)
- `packages/` modular domain/runtime packages
- `examples/` workflow, web, and email demos
- `docs/execution/` frozen execution pack and build spec
- `docs/adr/` architecture decision records
- `tests/` unit, integration, property, replay, and load tests

## Quickstart

```bash
make setup
make precommit-install
make lint
make typecheck
make test
make run-embedded
make seed-demo-data
```

For a full machine setup and service compose workflow, use:

- `docs/execution/PACKAGING_INSTALL_FLOW.md`

## Local pre-commit guardrails

Install hooks once per clone:

```bash
make precommit-install
```

Run hooks against staged changes:

```bash
make precommit-run
```

Run hooks against the entire repository:

```bash
make precommit-run-all
```

Hook policy:

- `ruff check --fix` + `ruff format` on Python files
- hygiene checks (YAML/JSON/merge-conflicts/whitespace)
- gitleaks secret scan
- pre-push checks for `mypy` and TypeScript typecheck

## Required commands

The command surface is intentionally stable for automation:

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

## Profiles

Caliper uses profile-driven config:

- `embedded`: SQLite + local artifacts
- `service`: Postgres + API + worker
- `shared`: service profile + auth/workspace scoping

Use the deployment examples in `deploy/env/`:

- `deploy/env/.env.embedded.example`
- `deploy/env/.env.service.example`
- `deploy/env/.env.shared.example`

Set `CALIPER_PROFILE` and related env vars to switch mode. Shared mode enables auth by default and supports `CALIPER_SHARED_API_TOKEN` for basic secret-backed API access.
