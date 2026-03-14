# Job state machine and approvals

Chunk: **P2-004 Job state machine and approvals**

## Endpoints

- `POST /v1/jobs/{job_id}/pause`
- `POST /v1/jobs/{job_id}/resume`
- `POST /v1/jobs/{job_id}/archive`
- `GET /v1/jobs/{job_id}/audit`

All write endpoints require:

```json
{
  "workspace_id": "ws_demo",
  "approval_state": "approved"
}
```

`approval_state` is optional; when omitted on `resume`, it defaults to `approved`.

## Allowed transitions

- `draft` -> `shadow`, `active`, `archived`
- `shadow` -> `active`, `paused`, `archived`
- `active` -> `paused`, `completed`, `archived`
- `paused` -> `active`, `completed`, `archived`
- `completed` -> `archived`
- `archived` -> _(terminal)_

Invalid transitions return `409 Conflict`.

## Approval state

Jobs now persist `approval_state` with values:

- `not_required`
- `pending`
- `approved`
- `rejected`

This state can be updated as part of pause/resume/archive transitions.

## Audit trail

Each state transition appends an audit action (`job.pause`, `job.resume`, `job.archive`) including:

- `from_status`
- `to_status`
- `approval_state`

Audit records are queryable via `GET /v1/jobs/{job_id}/audit?workspace_id=...`.
