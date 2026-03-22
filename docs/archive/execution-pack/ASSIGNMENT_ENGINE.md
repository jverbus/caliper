# Assignment Engine Interface and Fixed Split Policy

This chunk implements the phase-3 assignment substrate (`P3-001`) used by later API work.

## Components

- `AssignmentEngine` (`packages/py-caliper-policies/src/caliper_policies/engine.py`)
- `AssignmentError` for safe hard-fail behavior when no eligible arms are available

## Assignment flow

1. Filter arms to eligible active arms in the requested workspace/job.
2. If `candidate_arms` is supplied in the request, intersect eligible arms with that subset.
3. Resolve fixed-split weights from `job.policy_spec.params.weights`.
4. Normalize configured weights; if invalid/missing/zero, fall back to equal weights across eligible arms.
5. Produce a deterministic weighted draw from `(job_id, unit_id, idempotency_key)`.
6. Return an `AssignResult` with:
   - chosen arm
   - propensity
   - policy family/version
   - candidate arms considered
   - diagnostics (`scores`, `reason`, `fallback_used`)

## Determinism and explainability

- Draws are deterministic for a fixed `(job_id, unit_id, idempotency_key)` tuple.
- Diagnostics include per-arm normalized weights and explicit selection reason.
- Propensity is always the selected arm weight in the decision set.

## Test coverage

`tests/unit/test_assignment_engine.py` validates:

- candidate-arm subset behavior,
- weighted fixed-split behavior over a large request sample,
- equal-weight fallback when configured weights are absent.
