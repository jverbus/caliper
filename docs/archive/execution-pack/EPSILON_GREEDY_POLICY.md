# Epsilon-Greedy Policy

This chunk implements Phase 4 task `P4-001` by adding epsilon-greedy assignment behavior to the policy engine.

## Behavior

`AssignmentEngine` now routes assignment weight resolution by `policy_family`:

- `fixed_split` keeps existing weighted behavior.
- `epsilon_greedy` computes a mixed strategy from:
  - `params.epsilon` (default `0.1`, clamped to `[0, 1]`)
  - `params.value_estimates` map (`arm_id -> estimated value`, defaults to `0.0`)

For epsilon-greedy:

1. Determine best estimated arm(s) from `value_estimates` among currently eligible arms.
2. Allocate exploration weight evenly across all eligible arms: `epsilon / N`.
3. Allocate exploitation weight evenly across best arm(s): `(1 - epsilon) / K`.
4. Final arm weight is `explore + exploit_if_best`.

Diagnostics use reason `epsilon_greedy_policy`, and propensity always equals the chosen arm probability.

## Deterministic selection

The existing deterministic draw (`job_id`, `unit_id`, `idempotency_key`) is reused, so retries remain stable for the same request identity.

## Test coverage

`tests/unit/test_assignment_engine.py` now includes epsilon-greedy tests for:

- preference toward higher-value arms in seeded simulation,
- valid propensity/diagnostics output,
- fixed-split fallback diagnostics behavior preserved.
