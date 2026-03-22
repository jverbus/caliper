# Projection Rebuild Support

Chunk: **P1-005 Projection rebuild support**

## What this adds

- Projection rebuild runner (`rebuild_job_projections`) that replays events and recomputes per-arm aggregates.
- Aggregate projection table refresh for assignment/exposure/outcome counters (`projection_metrics`).
- Projection rebuild audit trail (`projection_rebuild_audit`) including event count and time-window metadata.

## Rebuild behavior

The rebuild runner:

1. Replays events from `event_ledger` for a `(workspace_id, job_id)` scope (optional `start`/`end` window).
2. Aggregates by arm for canonical decision-loop event types:
   - `decision.assigned` → `assignments`
   - `decision.exposed` → `exposures`
   - `outcome.observed` → `outcomes`
3. Replaces the scoped aggregate rows in `projection_metrics`.
4. Appends a rebuild-audit record in `projection_rebuild_audit`.

## API surface

- `rebuild_job_projections(repository, workspace_id, job_id, start=None, end=None)`
- `SQLRepository.replace_projection_metrics(...)`
- `SQLRepository.list_projection_metrics(...)`
- `SQLRepository.record_projection_rebuild(...)`
- `SQLRepository.list_projection_rebuild_audits(...)`

## Acceptance mapping

- **Projections can be rebuilt from stored events:** verified by integration test replaying `event_ledger` and asserting persisted projection aggregates.
- **Report fixtures remain consistent after rebuild:** rebuild performs deterministic full replacement for scoped aggregates, avoiding additive drift across reruns.
