# Backup and restore runbook verification

Chunk: `P8-004 Backup and restore runbook verification`

This runbook verifies local backup and restore for embedded-mode data and reports.

## 1) Prepare deterministic local data

```bash
mkdir -p data reports exports
make seed-demo-data
```

## 2) Create backup archive

```bash
PYTHONPATH=packages/py-caliper-core/src:packages/py-caliper-storage/src:packages/py-caliper-events/src:packages/py-caliper-policies/src:packages/py-caliper-reward/src:packages/py-caliper-reports/src:packages/py-caliper-adapters/src:packages/py-sdk/src:apps \
uv run python scripts/backup_restore.py backup \
  --repo-root . \
  --data-dir data \
  --reports-dir reports \
  --output-file exports/caliper-backup-test.tar.gz
```

Expected result: JSON output containing `archive` and `tracked_paths`.

## 3) Restore into a clean target

```bash
mkdir -p /tmp/caliper-restore-check
rm -rf /tmp/caliper-restore-check/*
uv run python scripts/backup_restore.py restore \
  --archive-file exports/caliper-backup-test.tar.gz \
  --target-root /tmp/caliper-restore-check
```

Expected result: JSON output containing `restored_paths` with `data` and `reports`.

## 4) Smoke-check restored artifacts

```bash
test -f /tmp/caliper-restore-check/data/seed/workflow-demo.db
test -f /tmp/caliper-restore-check/reports/seed/workflow/report.md
test -f /tmp/caliper-restore-check/manifest.json
```

## 5) Acceptance mapping

- Export script: `scripts/backup_restore.py backup`
- Restore script: `scripts/backup_restore.py restore`
- Runbook walkthrough: sections 1-4
- Restore smoke test: section 4 + `tests/unit/test_backup_restore.py`
