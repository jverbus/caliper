# Reward Engine (P3-005)

This chunk introduces a deterministic reward engine that evaluates configured objective formulas, applies penalties, and emits a normalized policy-update dataset.

## Scope

- Added `RewardEngine` in `py-caliper-reward`.
- Added formula evaluation for reward and penalty expressions using safe arithmetic syntax.
- Added attribution-window filtering so delayed outcomes outside the window are excluded.
- Added normalized reward dataset output (`RewardRecord`) for future policy-update loops.
- Added unit fixtures covering reproducibility and penalty/cost impact behavior.

## Evaluation model

For each `OutcomeCreate` event bundle:

1. Aggregate numeric metrics by `outcome_type` (for example `conversion`, `cost`, `latency_ms`).
2. Evaluate `objective_spec.reward_formula` against that metric map.
3. Evaluate each penalty expression in `objective_spec.penalties`.
4. Apply only positive penalties (`max(0, penalty_value)`) to avoid accidental reward boosts.
5. Produce scalar reward.

Missing metrics default to `0.0` for formula safety.

## Normalized policy-update dataset

`build_policy_update_dataset(...)` joins outcomes to known decisions and emits records with:

- decision identity (`workspace_id`, `job_id`, `decision_id`, `unit_id`, `arm_id`)
- propensity
- raw `reward`
- `normalized_reward` in `[0, 1]`
- `observed_at`
- expanded `metrics`

Normalization uses min/max across the resulting batch. If all rewards are equal, each record receives `normalized_reward = 1.0`.

## Acceptance mapping

- **Reward values reproducible from fixtures:** unit test validates deterministic reward math from fixed fixture values.
- **Penalties and costs affect updates correctly:** unit tests verify explicit cost and penalty impact and verify out-of-window outcomes are excluded from update datasets.
