# PV1-003 OBP integration

## Scope

Integrate Open Bandit Pipeline (OBP) into Caliper's replay/OPE scaffold so replay datasets can be prepared and scored with standard off-policy estimators.

## Delivered

- Added OBP prep contract in `caliper_ope.estimators`:
  - `OBPPreparedData`
  - `prepare_obp_data(records)`
- Added OBP execution helper:
  - `estimate_policy_value_with_obp(records, estimator="dr"|"ipw")`
- Added explicit integration error type:
  - `OBPIntegrationError`
- Exported OBP helpers via `caliper_ope.__init__`.
- Added unit coverage for:
  - replay→OBP payload shaping,
  - required evaluation-policy probabilities,
  - estimator selection + OBP call path.

## Replay context contract for OBP

For each replay row, include in `record.context`:

- `obp_evaluation_probs`: `{arm_id: probability}` for the evaluation policy at that round.

Optional numeric scalar keys in context are emitted as OBP context features.

## Notes

- OBP remains an optional runtime dependency in this chunk.
- If OBP is unavailable, helpers raise `OBPIntegrationError` with install guidance (`uv pip install obp`).
- This chunk intentionally focuses on a stable integration seam; richer estimators and policy-learning workflows can build on this API in later chunks.
