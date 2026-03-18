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

For full machine setup + hardening runbooks, use:

- `docs/execution/PACKAGING_INSTALL_FLOW.md`
- `docs/execution/BACKUP_RESTORE_RUNBOOK.md`

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
- `make run-landing-page-demo`
- `make run-email-demo`
- `make run-embedded`
- `make run-service`
- `make run-worker`
- `make seed-demo-data`
- `make backup-local`
- `make restore-local`

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

## Demo orchestrator entrypoints

Top-level scripts for automated demo orchestration:

- `./run_landing_page_demo --topic "..." --variant-count 5 --mode dry_run`
- `./run_landing_page_demo --topic "..." --variant-count 5 --mode serve_only --backend embedded --observe-seconds 180`
- `./run_landing_page_demo --topic "..." --variant-count 5 --mode serve_and_simulate --backend embedded`
- `./run_landing_page_demo --topic "..." --variant-count 5 --mode live` (alias for `serve_and_simulate`)
- `./run_landing_page_demo --topic "..." --variant-count 5 --mode serve_only --open-tunnel`
- `./run_email_demo --topic "..." --recipients "a@example.com,b@example.com" --variant-count 5 --mode dry_run --backend embedded`
- `./run_email_demo --topic "..." --recipients "a@example.com,b@example.com" --variant-count 5 --mode dry_run --backend service --api-url http://127.0.0.1:8000`
- `./run_email_demo --topic "..." --recipients "a@example.com,b@example.com" --variant-count 5 --mode live --backend embedded`
- `./run_email_demo --topic "..." --recipients "a@example.com,b@example.com" --variant-count 5 --mode dry_run --open-tunnel`
- `scripts/run_landing_demo_with_tunnel.sh` / `scripts/run_email_demo_with_tunnel.sh` one-command tunnel helpers

Mode semantics (current):

- Landing `dry_run`: synthetic in-process simulation.
- Landing `serve_only`: real FastAPI demo server + tracked routes, no synthetic traffic driver.
- Landing `serve_and_simulate`: real FastAPI demo server + synthetic visitor driver against real endpoints.
- Landing `live`: alias for `serve_and_simulate`.
- Landing supports `--backend embedded|service` for the same orchestrator flow.
- Landing served modes support `--public-base-url https://...` or `--open-tunnel` for externally reachable links.
- Email supports `--backend embedded|service`.
- Email supports `--public-base-url https://...` or `--open-tunnel` for canonical tracked/report URLs.
- Email starts a tracking server (`apps.demo_email`) and wires per-recipient links to tracked routes:
  - `/email/{job_id}/click`
  - `/email/{job_id}/convert`
  - `/email/{job_id}/reply`
- Email `dry_run`: synthetic provider + synthetic tracked-route driver (click/conversion/reply).
- Email `live`: **real Gmail SMTP send path only**; command fails fast if Gmail credentials are missing.
  - By default, `live` does **not** inject synthetic tracked events.
  - Use `--simulate-tracked-events` to force synthetic route hits in `live` mode.
- Reply signal first-step ingest command: `uv run python scripts/ingest_email_reply_signal.py ...`

Each run writes report artifacts plus a machine-readable `winner_summary.json` manifest under `reports/landing_page_demo/<mode>/` or `reports/email_demo/<mode>/`.
Both manifests are canonicalized with backend/mode/provider semantics, URLs, measurement metadata, metrics, and artifact paths (email adds tracked-route + reply-ingest details).

Tunnel safety notes:

- Treat quick tunnels as temporary public exposure of your local demo endpoints.
- Use demo/synthetic data only while a tunnel is active.
- End the run (or press `Ctrl-C`) immediately after walkthroughs to close server + tunnel.
