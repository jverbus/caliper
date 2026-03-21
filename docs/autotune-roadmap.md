# Caliper Autotune Roadmap (Simulation-Only, Human-Gated)

## One-line summary

Build a **simulation-only, fixed-evaluator, keep/discard autotune lane** on top of Caliper’s existing MCP + `DecisionSummary` surfaces, while keeping all production rollout actions human-gated.

---

## Goals

- Reuse Caliper’s canonical analytics/decision surfaces for objective scoring.
- Make candidate evaluation reproducible and comparable (frozen simulation settings + seed).
- Keep editable surface intentionally small in v1.
- Persist every candidate/run/result/promotion artifact durably (including failures).
- Require explicit human confirmation for promotion.

## Non-goals (v1)

- No autonomous production rollout.
- No automatic traffic changes.
- No edits to decision/analytics core logic by autotune candidates.
- No UI-first implementation; MCP and tests come first.

---

## Milestone 0 — Guardrail rollback blocker

### Problem
`decision_service.get_decision_summary()` currently constructs `DecisionRuleInput` with `guardrail_regression=None`, preventing real guardrail-driven rollback recommendations from computed signals.

### Tasks
- Compute and pass real `guardrail_regression` in `decision_service.py`.
- Keep existing `DecisionSummary` schema unchanged.
- Add tests proving simulated guardrail breach produces `ROLLBACK`.

### Acceptance
- Configured guardrail regression can switch `DecisionSummary.recommendation` to `ROLLBACK`.
- No MCP/UI contract changes.

---

## Milestone 1 — Autotune domain model + persistence

### New data models/collections
- `AutotuneCandidate`
- `AutotuneRun`
- `AutotuneResult`
- `AutotunePromotion`

### Suggested fields
- **candidate**: `candidate_id`, `experiment_id`, `candidate_type`, `parent_candidate_id`, `editable_surface`, `content`, `complexity_score`, `created_at`
- **run**: `run_id`, `candidate_id`, `baseline_candidate_id`, `simulation_config_snapshot`, `seed`, `budget`, `status`, `started_at`, `ended_at`, `evaluator_version`
- **result**: `score`, `score_breakdown`, `decision_summary_snapshot`, `analytics_snapshot`, `keep_discard`, `reason`, `hard_fail_code`
- **promotion**: `candidate_id`, `promoted_by`, `target_surface`, `confirmation`, `created_at`, `diff_summary`

### Files
- `pythonServerExperimentation/app/data_models/experimentation/autotune_models.py`
- `pythonServerExperimentation/app/services/autotune/`

### Indexes
- `candidate_id`, `run_id`, `experiment_id`, `status`, `created_at`

### Acceptance
- Candidates/runs/results/promotions remain queryable across restarts.
- Failed runs are retained and visible.

---

## Milestone 2 — Fixed evaluator + deterministic simulation harness

### Evaluation chain (canonical)
1. create/update candidate experiment config
2. `simulation_run`
3. `simulation_status`
4. `analytics_get`
5. `decision_summary_get`
6. final scalar score

### Frozen evaluator inputs
- simulation mode
- segments
- synthetic user/event budget
- seed
- runtime window

If deterministic seed support is missing in simulation config, add it first.

### Scoring rules
- Hard fail if `DecisionSummary.recommendation == ROLLBACK`
- Hard fail on SRM/data-quality gate failures
- Else: `score = normalized_primary_metric_improvement + health_bonus + confidence_bonus - complexity_penalty`

### Acceptance
- Same candidate + same seed yields same score within tolerance.
- Baseline/candidate comparisons use fixed traffic budget and frozen evaluator settings.

---

## Milestone 3 — Tiny editable surface (v1 constraints)

### Allowed surfaces
- MCP prompt text
- `caliper://agent_playbook` content
- experiment template JSON
- demo ad-copy generation inputs/templates
- closed-loop demo scenario definitions

### Read-only surfaces (v1)
- `decision_engine.py`
- `decision_service.py`
- analytics math
- status recommendation builder
- rollout endpoints
- `DecisionSummary` schema

### Acceptance
- Candidate creation rejects forbidden surfaces.
- Evaluator path is identical between baseline and candidates.

---

## Milestone 4 — Keep/discard loop over MCP

### MCP tools
- `autotune_candidate_create`
- `autotune_candidate_list`
- `autotune_run`
- `autotune_status`
- `autotune_result_get`
- `autotune_keep`
- `autotune_discard`
- `autotune_promote`
- `autotune_export_jsonl`

### Loop logic
1. snapshot baseline
2. generate one candidate
3. evaluate baseline (if missing)
4. evaluate candidate (fixed simulation budget)
5. compare candidate vs baseline
6. keep only if:
   - no hard fail
   - score > baseline + delta
   - complexity penalty acceptable
7. otherwise discard
8. repeat

### Complexity penalty inputs
- prompt length delta
- number of changed fields
- number of non-default knobs touched
- number of artifacts touched

### Acceptance
- At least one kept and one discarded candidate with explicit reasons.
- No candidate auto-changes production behavior.

---

## Milestone 5 — Human-gated promotion + auditability

### Promotion behavior
Promotion does one of:
- write candidate into versioned artifact file/resource, or
- open PR-style patch/diff for review.

Promotion never:
- activates experiments automatically,
- changes live traffic automatically,
- bypasses rollout approvals.

### Required controls
- explicit confirmation token for `autotune_promote`
- audit log entry
- diff summary with “what changed” + “why better than baseline”
- pre-promotion replay check using frozen evaluator config

### Acceptance
- Promotion requires explicit human action.
- Promoted content + metadata are durably recorded.

---

## Milestone 6 — First proving ground: closed-loop website demo

### Initial target scope
- only demo ad-copy generate inputs/prompt wording/template
- evaluate on website recommendation or ad-copy demo
- compare via simulation-backed runs only

### Expansion sequence
1. website/demo path
2. email flow
3. generalized playbook tuning
4. decision-policy config tuning (v2)

### Acceptance
- End-to-end demo baseline vs candidate prompt under fixed simulation budget.
- Score comparison + keep/discard outcome visible through MCP.

---

## Milestone 7 (v2) — Externalize decision policy

Move hardcoded thresholds into versioned `DecisionPolicyConfig`, preserving default behavior exactly.

Current hardcoded behavior to preserve:
- ship threshold = `max(confidence_threshold, 0.95)`
- ramp-50 threshold = `max(confidence_threshold, 0.90)`

### Acceptance
- Default policy config reproduces existing outputs exactly.
- Alternate policy configs evaluable in simulation only (not auto-promoted).

---

## Milestone 8 — Docs, MCP resources/prompts, and tests before UI

### Docs/resources/prompts
- `docs/autotune.md`
- `docs/autotune-ops.md`
- `caliper://autotune_playbook`
- MCP prompts:
  - `autotune_candidate_prompt`
  - `autotune_run_prompt`
  - `autotune_promotion_prompt`

### Tests
- unit: score calculation, keep/discard logic, complexity penalty
- integration: candidate → simulation → analytics → decision summary → result
- safety: forbidden-surface rejection, promotion confirmation requirement
- reproducibility: same seed => same result

Use the repo’s existing MCP integration-test workflow as baseline harness.

---

## Concrete implementation order

1. Wire real `guardrail_regression` in `decision_service.py`
2. Add autotune models + Mongo collections
3. Add fixed evaluator service (`simulation_run`/`analytics_get`/`decision_summary_get`)
4. Add MCP tools/resources/prompts for autotune
5. Restrict editable surfaces to prompt/resource/template artifacts
6. Run first closed-loop demo on ad-copy/website scenario
7. Add human-gated promotion flow
8. Externalize decision policy into config
9. Add UI only after MCP-only loop succeeds

---

## Definition of done (Milestone 1 complete)

Done when all are true:
- baseline + candidate can be generated for one narrow artifact surface
- both evaluated with identical simulation budget and seed
- winner chosen by fixed scorer built from canonical Caliper outputs
- every run logged durably with keep/discard reasoning
- no rollout action auto-executed
- promotion requires human confirmation
- full loop works end-to-end through MCP on one demo scenario
