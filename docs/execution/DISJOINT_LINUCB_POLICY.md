# Disjoint LinUCB policy

Post-v1 contextual baseline policy family: `disjoint_linucb`.

## Policy contract

Set `PolicySpec.policy_family = "disjoint_linucb"`.

Supported `policy_spec.params`:

- `alpha` (float, default `1.0`): exploration multiplier.
- `feature_order` (optional list[str]): key order when `context.features` is a map.
- `feature_dim` (optional int): fallback dimension when request context omits features.
- `linucb_state` (optional map): per-arm state payload with:
  - `a`: square matrix (d x d)
  - `b`: vector (d)

`context.features` can be either a list of floats or a map keyed by `feature_order`.

## Selection behavior

For each eligible active arm:

1. Read per-arm disjoint state (`A`, `b`), defaulting to identity/zero if missing.
2. Compute `theta = A^-1 b`.
3. Compute UCB score: `x^T theta + alpha * sqrt(x^T A^-1 x)`.
4. Choose max-score arm(s); ties split propensity equally.

Diagnostics:

- `reason = "disjoint_linucb_policy"`
- `scores` stores final propensities
- `fallback_used = true` only when a valid feature vector cannot be built
