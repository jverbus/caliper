from __future__ import annotations

import json
import math
from typing import Any

from caliper_core.models import AutotuneCandidate, AutotuneResult, AutotuneRun
from fastapi import HTTPException

from apps.api.autotune_evaluator import CandidateConfig, FrozenEvaluatorConfig, evaluate_fixed_score
from apps.api.services.autotune_policy import autotune_disposition, derived_complexity_score

ALLOWED_AUTOTUNE_EDITABLE_SURFACES = {
    "mcp_prompt_text",
    "caliper://agent_playbook",
    "experiment_template_json",
    "demo_ad_copy_templates",
    "demo_scenario_definitions",
}

AUTOTUNE_PROMOTION_CONFIRMATION = "CONFIRM_AUTOTUNE_PROMOTION"

__all__ = [
    "ALLOWED_AUTOTUNE_EDITABLE_SURFACES",
    "AUTOTUNE_PROMOTION_CONFIRMATION",
    "autotune_diff_summary",
    "autotune_disposition",
    "derived_complexity_score",
    "run_promotion_replay_check",
    "serialize_promotion_diff",
    "to_candidate_config",
    "validate_autotune_confirmation",
    "validate_autotune_editable_surface",
]


def autotune_diff_summary(
    *,
    candidate: AutotuneCandidate,
    baseline: AutotuneCandidate,
    result: AutotuneResult,
) -> str:
    changed_top_level = sorted(
        key
        for key in set(candidate.content.keys()) | set(baseline.content.keys())
        if candidate.content.get(key) != baseline.content.get(key)
    )
    delta = result.score_breakdown.get("delta_vs_baseline", result.score)
    changed = ", ".join(changed_top_level) if changed_top_level else "no top-level fields"
    return (
        f"what_changed: {changed}; "
        f"why_better: candidate score delta vs baseline = {delta:.4f}, "
        f"disposition={result.keep_discard}"
    )


def to_candidate_config(
    candidate: AutotuneCandidate,
    *,
    complexity_score: float | None = None,
) -> CandidateConfig:
    return CandidateConfig(
        candidate_id=candidate.candidate_id,
        content=candidate.content,
        complexity_score=(
            candidate.complexity_score if complexity_score is None else complexity_score
        ),
    )


def run_promotion_replay_check(
    *,
    candidate: AutotuneCandidate,
    baseline: AutotuneCandidate,
    run: AutotuneRun,
    result: AutotuneResult,
) -> dict[str, Any]:
    frozen = FrozenEvaluatorConfig(
        seed=run.seed,
        synthetic_user_budget=run.budget,
        **run.simulation_config_snapshot,
    )
    replay_candidate_complexity, _ = derived_complexity_score(
        candidate_content=candidate.content,
        baseline_content=baseline.content,
        declared_complexity_score=candidate.complexity_score,
    )
    replay_candidate = evaluate_fixed_score(
        candidate=to_candidate_config(candidate, complexity_score=replay_candidate_complexity),
        frozen_config=frozen,
    )
    replay_baseline = evaluate_fixed_score(
        candidate=to_candidate_config(baseline),
        frozen_config=frozen,
    )
    replay_delta = replay_candidate.score - replay_baseline.score
    expected_delta = result.score_breakdown.get("delta_vs_baseline", result.score)
    if math.isinf(replay_delta) and math.isinf(expected_delta) and (replay_delta == expected_delta):
        delta_diff = 0.0
    else:
        delta_diff = abs(replay_delta - expected_delta)
    expected_recommendation = result.decision_summary_snapshot.get("recommendation")
    passed = delta_diff <= 1e-9 and replay_candidate.recommendation.value == expected_recommendation

    def safe_float(value: float) -> float | str:
        return value if math.isfinite(value) else str(value)

    return {
        "passed": passed,
        "expected_delta_vs_baseline": safe_float(expected_delta),
        "actual_delta_vs_baseline": safe_float(replay_delta),
        "delta_diff": safe_float(delta_diff),
        "expected_recommendation": result.decision_summary_snapshot.get("recommendation"),
        "actual_recommendation": replay_candidate.recommendation.value,
        "seed": run.seed,
        "budget": run.budget,
        "simulation_config_snapshot": run.simulation_config_snapshot,
    }


def validate_autotune_editable_surface(surface: str) -> str:
    normalized = surface.strip()
    if normalized not in ALLOWED_AUTOTUNE_EDITABLE_SURFACES:
        allowed = ", ".join(sorted(ALLOWED_AUTOTUNE_EDITABLE_SURFACES))
        raise HTTPException(
            status_code=400,
            detail=(
                f"editable_surface '{surface}' is not allowed in v1. Allowed surfaces: {allowed}"
            ),
        )
    return normalized


def validate_autotune_confirmation(confirmation: str) -> None:
    if confirmation.strip() != AUTOTUNE_PROMOTION_CONFIRMATION:
        raise HTTPException(
            status_code=400,
            detail=(f"confirmation token mismatch; use '{AUTOTUNE_PROMOTION_CONFIRMATION}'"),
        )


def serialize_promotion_diff(
    *,
    summary: str,
    run_id: str,
    promoted_content: dict[str, Any],
    replay_check: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "summary": summary,
            "run_id": run_id,
            "promoted_content": promoted_content,
            "replay_check": replay_check,
        },
        sort_keys=True,
    )
