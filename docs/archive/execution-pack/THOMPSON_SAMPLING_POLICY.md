# Thompson Sampling policy

Chunk: **P4-003 Thompson sampling**

## Summary

Caliper now supports a Bernoulli Thompson Sampling policy family (`thompson_sampling`) in the assignment engine.

The policy:

- samples one Beta posterior draw per eligible arm,
- normalizes sampled values into assignment weights/propensities,
- returns those normalized weights in diagnostics.

Sampling is deterministic per assignment request by seeding from `(job_id, unit_id, idempotency_key, optional seed_salt)` so retries with the same idempotency key are stable.

## Policy parameters

`policy_spec.params` supports:

- `alpha`: object map `{arm_id: float}` (success pseudo-count; default `1.0`)
- `beta`: object map `{arm_id: float}` (failure pseudo-count; default `1.0`)
- `seed_salt`: optional string to rotate deterministic sample streams without changing request identifiers

Any non-positive alpha/beta values are clamped to a tiny positive floor to keep Beta sampling valid.

## Diagnostics

`decision.diagnostics` for Thompson Sampling includes:

- `reason = "thompson_sampling_policy"`
- `scores` = normalized sampled values per arm (sum to 1)
- `fallback_used` false in normal operation

## Acceptance mapping

- **Policy shifts traffic toward better arms in seeded simulation**:
  covered by `test_thompson_sampling_shifts_traffic_toward_better_arms`.
- **Diagnostics are present**:
  covered by `test_thompson_sampling_emits_diagnostics`.
