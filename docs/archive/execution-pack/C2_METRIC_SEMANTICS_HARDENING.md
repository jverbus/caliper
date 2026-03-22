# C2: metric semantics hardening (rate/count/denominator correctness)

This chunk hardens reward-metric semantics so formula evaluation is deterministic and mathematically correct for mixed metric shapes.

## What ships

- Extends `OutcomeEvent` with optional metric semantics fields:
  - `metric_kind` (`value`, `count`, `rate`; default `value`)
  - `denominator` (required for `rate`)
- Updates reward metric aggregation behavior:
  - `value`/`count` metrics aggregate by sum.
  - `rate` metrics aggregate as weighted rates: `sum(rate * denominator) / sum(denominator)`.
- Exposes explicit rate math terms for formulas:
  - `<metric>__numerator`
  - `<metric>__denominator`
- Enforces correctness invariants:
  - `rate` metrics with missing/non-positive denominators raise `RewardFormulaError` instead of silently producing skewed values.

## Why this matters

Raw averaging of rate points can significantly misstate performance when denominator volume differs across events. Weighted aggregation preserves statistical correctness and keeps report/reward calculations aligned with real traffic.

## Acceptance mapping

- ✅ Rate metrics respect denominator-weighted semantics.
- ✅ Count/value metrics remain backward-compatible via additive behavior.
- ✅ Invalid rate inputs fail fast with explicit errors.
- ✅ Unit tests cover weighted aggregation and denominator validation.
