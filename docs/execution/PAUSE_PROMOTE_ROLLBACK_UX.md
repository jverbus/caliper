# P8-002 Pause, promote, and rollback UX

This chunk hardens operator controls around lifecycle and policy safety actions.

## API flows

- `POST /v1/jobs/{job_id}/pause`
- `POST /v1/jobs/{job_id}/resume`
- `POST /v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/promote`
  - UX alias for snapshot activation to match operator language.
- `POST /v1/jobs/{job_id}/policy-snapshots/rollback`
- `GET /v1/jobs/{job_id}/audit?workspace_id=...`

All actions emit auditable records in `audit_log`:

- `job.pause`
- `job.resume`
- `policy.snapshot.activated`
- `policy.snapshot.rollback`

## CLI flows

- `pause-job`
- `resume-job`
- `promote-policy`
- `rollback-policy`
- `job-audit`

## Acceptance mapping

- Operators can pause/resume and promote/rollback policy snapshots through both API and CLI.
- Audit records are visible from the API (`job-audit` in CLI).
- Integration tests assert rollback correctness by verifying assignment policy version before/after rollback.
