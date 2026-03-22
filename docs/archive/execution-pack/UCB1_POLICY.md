# UCB1 Policy

This chunk implements Phase 4 task `P4-002` by adding UCB1 assignment behavior to the policy engine.

## Behavior

`AssignmentEngine` now supports `policy_family=ucb1` and computes per-arm weights from configured estimates:

- `params.mean_rewards`: map of `arm_id -> empirical mean reward` (defaults to `0.0`)
- `params.pull_counts`: map of `arm_id -> observed pull count` (defaults to `0`)
- `params.exploration_c`: exploration multiplier (default `1.0`, clamped to `>= 0`)

For non-cold-start arms, the UCB1 score is:

`mean_reward + exploration_c * sqrt((2 * ln(total_pulls)) / pull_count)`

Scores are normalized into probabilities so deterministic draw + weighted selection continues to return a valid propensity.

## Cold start

If any eligible arm has `pull_count <= 0`, the engine routes uniformly across unseen arms and assigns zero probability to already-seen arms for that decision step.

This guarantees new arms receive initial exploration and avoids divide-by-zero instability.

## Deterministic selection

The existing deterministic draw seed (`job_id`, `unit_id`, `idempotency_key`) is unchanged, so retries remain stable for identical request identity.

## Test coverage

`tests/unit/test_assignment_engine.py` now includes UCB1 tests for:

- preference toward higher-value arms in seeded simulation,
- cold-start handling with uniform unseen-arm allocation,
- valid propensity and diagnostics behavior for UCB1 decisions.
