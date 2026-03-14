# P2-003 Arm Bulk Registration and Lifecycle

This chunk adds API support for registering many arms at once and managing arm lifecycle transitions.

## Endpoints

### `POST /v1/jobs/{job_id}/arms:batch_register`

Registers a batch of arms for a job in a single request.

Request body:

```json
{
  "workspace_id": "ws-demo",
  "arms": [
    {
      "arm_id": "arm_001",
      "name": "Variant A",
      "arm_type": "artifact",
      "payload_ref": "s3://bucket/a.json",
      "metadata": {"locale": "en-US"}
    }
  ]
}
```

Behavior:

- Validates job existence and workspace match.
- Upserts each arm with constraints and metadata persisted.
- Emits audit entry: `arm.batch_register` with `registered_count`.

### `GET /v1/jobs/{job_id}/arms?workspace_id=...`

Lists arms for a job/workspace scope.

### `POST /v1/jobs/{job_id}/arms/{arm_id}:lifecycle`

Transitions arm lifecycle state.

Request body:

```json
{
  "workspace_id": "ws-demo",
  "action": "hold"
}
```

Supported actions:

- `hold` -> `held_out`
- `retire` -> `retired`
- `resume` -> `active`

Behavior:

- Validates job existence and workspace match.
- Returns 404 if arm does not exist in scope.
- Emits auditable state transitions:
  - `arm.hold`
  - `arm.retire`
  - `arm.resume`

## Acceptance coverage

Integration tests verify:

- batch registration with 120 arms (>=100 requirement),
- state transitions hold/retire/resume,
- metadata persistence on returned/listed arms,
- audit trail entries for register and lifecycle events,
- workspace and missing-entity error handling.
