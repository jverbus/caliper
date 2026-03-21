# Autotune Ops Runbook

Operational runbook for the simulation-only autotune lane.

## 1) Create baseline + candidate

- Baseline should represent current approved artifact.
- Candidate must target an allowlisted editable surface.

## 2) Run fixed evaluator

- Use one seed + one budget for both baseline and candidate.
- Keep `simulation_config_snapshot` frozen for comparability.

## 3) Inspect result

Check:

- `score_breakdown.candidate_score`
- `score_breakdown.baseline_score`
- `score_breakdown.delta_vs_baseline`
- `keep_discard`
- `reason`
- `hard_fail_code` (if present)

## 4) Human disposition

- Optionally override using keep/discard endpoints.
- Record explicit reason for audit clarity.

## 5) Promotion (human-gated only)

Promotion requires:

- `confirmation = CONFIRM_AUTOTUNE_PROMOTION`
- candidate/run consistency
- replay check pass

If replay check fails, do **not** promote.

## 6) Export artifacts

Use `/v1/autotune/export.jsonl` for experiment audit trails.

## Incident posture

- Never bypass confirmation token checks.
- Never auto-execute rollout actions from autotune results.
- Treat hard-fail rollback recommendations as discard signals for v1.
