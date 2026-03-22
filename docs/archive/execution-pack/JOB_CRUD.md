# Job CRUD (P2-002)

This chunk adds the initial `/v1/jobs` contract on top of the API skeleton.

## Endpoints

- `POST /v1/jobs` creates a job and returns `{ job_id, status, created_at }`.
- `GET /v1/jobs/{job_id}` returns the full job document.
- `PATCH /v1/jobs/{job_id}` applies a partial `JobPatch` update and returns the updated job.

All endpoints are wired through the shared repository dependency and honor the shared-profile bearer-token scaffold introduced in P2-001.

## Audit behavior

Write endpoints now append records to `audit_log`:

- `job.create` with `{ "status": "draft" }`
- `job.update` with `{ "patched_fields": [...] }`

This satisfies backlog acceptance requiring auditable writes for job mutations.

## Error handling

- `GET` / `PATCH` for unknown `job_id` returns `404` with a descriptive error message.

## Test coverage

`tests/integration/test_api_job_crud.py` validates:

- end-to-end create/read/update contract behavior
- audit records emitted for create + update writes
- 404 behavior for unknown jobs
