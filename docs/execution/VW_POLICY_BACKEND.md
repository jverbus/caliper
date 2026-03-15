# VW policy backend scaffold (PV1-002)

Post-v1 contextual backend policy family: `vw_cb_adf`.

This chunk adds a **backend seam** for VW CB-ADF style policies without taking a hard runtime dependency on the `vw` binary yet.

## Policy family

Set `PolicySpec.policy_family = "vw_cb_adf"`.

Supported scaffold params under `PolicySpec.params`:

- `arm_priors` (optional): map of `arm_id -> float` to bias traffic
- `temperature` (optional, default `1.0`): softmax temperature for normalized probabilities

## Request context contract (scaffold)

`POST /v1/assign` context may include:

- `shared_features`: `dict[str, number]`
- `arm_features`: `dict[arm_id, dict[str, number]]`

Non-numeric values are ignored in scaffold parsing.

## Backend behavior

`AssignmentEngine` routes `vw_cb_adf` assignments through `VWPolicyBackend`:

1. Build deterministic CB-ADF style example strings per arm.
2. Compute deterministic scaffold scores per arm from job/request/feature inputs.
3. Add optional `arm_priors`.
4. Softmax-normalize to assignment probabilities.

This preserves:

- deterministic idempotent assignment behavior,
- valid propensity logging,
- policy-family-specific diagnostics,
- a stable integration seam for real VW inference in a follow-up chunk.

## Diagnostics

Decision diagnostics for this family use:

- `reason = "vw_cb_adf_policy_backend_scaffold"`
- `scores = {arm_id: probability}`
- `fallback_used = false` (normal path)
