# P9-004 Contextual promotion gate scaffold

This chunk adds a **non-live contextual promotion gate** that must pass before a contextual runtime policy snapshot can be activated.

## What was added

### Contextual runtime tagging on policy snapshots

Policy snapshots are treated as contextual runtime candidates when either of these payload fields is present:

- `runtime: "contextual"`
- `requires_contextual_gate: true`

Non-contextual snapshots continue to activate as before.

### Non-live gate check endpoint

`GET /v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/contextual-gate?workspace_id=...`

Response shape:

- `snapshot_id`
- `is_contextual_runtime`
- `passed`
- `failures` (list of unmet gate checks)

An audit entry is written for every gate check:

- `policy.snapshot.contextual_gate.checked`

### Gate requirements for contextual snapshots

Contextual snapshots must include `payload.contextual_gate` with:

- `shadow_mode_validated: true`
- `ope_backtest_validated: true`
- `manual_review_approved: true`
- `context_schema_version` set

Additionally, at least one historical shadow evaluation must exist for the job:

- audit action `decision.shadow_evaluated`

### Activation safety rule

`POST /v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/activate` and
`POST /v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/promote`

now enforce contextual gate checks for contextual snapshots.

- If checks fail: HTTP 409 with structured failures and audit action `policy.snapshot.contextual_gate.blocked`
- If checks pass: activation proceeds and audit action `policy.snapshot.contextual_gate.passed` is written

## Acceptance mapping

- **Non-live gate checks for future contextual policies:** implemented via explicit gate endpoint + structured checks.
- **Policy state rules preventing accidental activation:** contextual snapshots cannot be activated/promoted unless gate checks pass.
- **Contextual runtime cannot be enabled without gate checks:** enforced in shared activation path used by both activate and promote endpoints.
