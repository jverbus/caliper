# Policy Snapshot Versioning

Chunk: **P4-004 Policy snapshot versioning**

## Summary

This chunk adds immutable policy snapshot storage with explicit activation and rollback flows.

- Snapshot creation persists immutable policy family/version/payload records.
- Snapshot activation marks exactly one active snapshot per job and emits `policy.updated`.
- Rollback re-activates a prior snapshot and emits `policy.updated` with rollback metadata.
- Assignment reads the active snapshot (if present) and uses only that version for decision policy parameters.

## API Surface

- `POST /v1/jobs/{job_id}/policy-snapshots`
- `GET /v1/jobs/{job_id}/policy-snapshots?workspace_id=...`
- `POST /v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/activate`
- `POST /v1/jobs/{job_id}/policy-snapshots/rollback`

## Assignment Behavior

`POST /v1/assign` now resolves an active snapshot before policy evaluation:

1. Load job policy spec
2. Load active snapshot for `(workspace_id, job_id)`
3. If active snapshot exists, use snapshot policy family + payload params + snapshot policy version
4. Produce assignment with the active snapshot version in `policy_version`

This guarantees assignment traffic is driven by the active snapshot only.

## Storage Notes

`policy_snapshots` now tracks:

- `is_active` boolean
- `activated_at` timestamp

Legacy databases are upgraded in-place by migration bootstrap.
