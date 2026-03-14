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
