# Packaging and install flow

Chunk: `P8-003 Packaging and install flow`

This runbook captures the minimum install path on a fresh machine, local data directory setup, seeded demo data, and service-mode compose flow.

## 1) Prerequisites

- Python 3.12+
- Node.js 20+
- `uv`
- `pnpm`
- Docker (for service mode)

## 2) Install from source

```bash
git clone https://github.com/jverbus/caliper.git
cd caliper
make setup
make lint
make typecheck
make test
```

## 3) Local data directories

Default local paths used in embedded mode:

- `./data/` SQLite databases and runtime state
- `./reports/` generated reports
- `./exports/` replay/export artifacts

Create explicitly (safe idempotent):

```bash
mkdir -p data reports exports
```

## 4) Seed demo data (embedded mode)

Generate deterministic demo databases and report artifacts:

```bash
make seed-demo-data
```

Outputs:

- seeded SQLite files in `data/seed/`
- report bundles in `reports/seed/{workflow,web,email}/`
- manifest in `reports/seed/manifest.json`

## 5) Service-mode compose flow

Start Postgres + API + worker:

```bash
docker compose -f deploy/compose/docker-compose.service.yml up -d
```

Check API health:

```bash
curl -sSf http://127.0.0.1:8000/health
```

Run service-mode demo against the API:

```bash
PYTHONPATH=packages/py-caliper-core/src:packages/py-caliper-storage/src:packages/py-caliper-events/src:packages/py-caliper-policies/src:packages/py-caliper-reward/src:packages/py-caliper-reports/src:packages/py-caliper-adapters/src:packages/py-sdk/src:apps \
uv run python examples/workflow_demo/demo.py --mode service --api-url http://127.0.0.1:8000
```

Tear down:

```bash
docker compose -f deploy/compose/docker-compose.service.yml down
```

## 6) Acceptance mapping

- Install instructions: sections 1-2
- Local data directory setup: section 3
- Seeded demo data: section 4 (`scripts/seed_demo_data.py`)
- Service-mode compose flow: section 5 (`deploy/compose/docker-compose.service.yml`)
