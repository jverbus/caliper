# Autotune (MCP-first, simulation-only)

This document describes the **MCP-only autotune loop** that must stay in place before any UI polish.

## Goals

- Run candidate-vs-baseline evaluations under identical frozen simulation settings.
- Compute decision outcomes from canonical analytics + decision summary logic.
- Persist keep/discard outcomes with explicit reasons.
- Keep rollout actions human-gated (no auto-promotion).

## Safety constraints (v1)

- Editable surfaces are allowlisted (prompt/resource/template artifacts only).
- Forbidden surfaces are rejected at candidate creation time.
- Promotion requires explicit confirmation token.
- Promotion includes deterministic replay verification against stored run/result.
- No automatic rollout execution.

## MCP endpoints used in the loop

- `POST /v1/autotune/candidates`
- `GET /v1/autotune/candidates`
- `POST /v1/autotune/runs`
- `GET /v1/autotune/runs/{run_id}/status`
- `GET /v1/autotune/runs/{run_id}/result`
- `POST /v1/autotune/runs/{run_id}/keep`
- `POST /v1/autotune/runs/{run_id}/discard`
- `POST /v1/autotune/promote`
- `GET /v1/autotune/export.jsonl`

## Playbook + prompts

- Resource: `caliper://autotune_playbook` → `docs/resources/autotune_playbook.md`
- Prompt: `autotune_candidate_prompt` → `docs/prompts/autotune_candidate_prompt.md`
- Prompt: `autotune_run_prompt` → `docs/prompts/autotune_run_prompt.md`
- Prompt: `autotune_promotion_prompt` → `docs/prompts/autotune_promotion_prompt.md`

## Test coverage expectations before UI

- Unit: scoring + keep/discard + complexity penalty behavior.
- Integration: candidate → simulation → analytics → decision summary → result.
- Safety: forbidden surface rejection + promotion confirmation required.
- Reproducibility: same seed + same inputs => same result.

Reference tests:

- `tests/unit/test_autotune_evaluator.py`
- `tests/unit/test_autotune_flow_logic.py`
- `tests/integration/test_api_autotune.py`
