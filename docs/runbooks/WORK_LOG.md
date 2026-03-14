# Work Log

## 2026-03-14

- Started chunk **P0-001 Repo scaffold**.
- Added full top-level scaffold layout (apps/packages/examples/deploy/tests/scripts) with placeholder entry points.
- Added scaffold import smoke test (`tests/unit/test_scaffold_imports.py`) to ensure placeholders import cleanly.
- Opened PR #1 for P0-001 and merged after validation (`54b9e60`).
- Started chunk **P0-002 Toolchain and CI**.
- Added uv + pnpm workspace config (`pyproject.toml`, `uv.lock`, `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`) and Make targets for setup/lint/typecheck/test.
- Added GitHub Actions CI workflow (`.github/workflows/ci.yml`) for quality, postgres smoke, and demo smoke jobs.
- Added placeholder integration/property tests plus Postgres smoke test to keep CI green on scaffold state.
- Fixed CI blocker after first PR run by pinning `packageManager` (`pnpm@10.23.0`) for `pnpm/action-setup@v4`.
- PR #2 for P0-002 merged (`63b9b8b`).
- Started chunk **P0-003 ADR and governance scaffolding**.
- Added ADR directory and template (`docs/adr/README.md`, `docs/adr/ADR-TEMPLATE.md`).
- Added pull request template (`.github/pull_request_template.md`) and work log template (`docs/runbooks/WORK_LOG_TEMPLATE.md`).
