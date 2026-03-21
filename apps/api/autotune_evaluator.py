from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from caliper_core.decision import DecisionRecommendation, DecisionSummary
from pydantic import BaseModel, Field

from apps.api.decision_service import get_decision_summary


class FrozenEvaluatorConfig(BaseModel):
    simulation_mode: str = "deterministic"
    segments: tuple[str, ...] = ()
    synthetic_user_budget: int = Field(default=1000, ge=1)
    synthetic_event_budget: int = Field(default=10000, ge=1)
    seed: int
    runtime_window_minutes: int = Field(default=60, ge=1)


class CandidateConfig(BaseModel):
    candidate_id: str
    content: dict[str, Any]
    complexity_score: float = Field(default=0.0, ge=0.0)


class SimulationRun(BaseModel):
    run_id: str
    candidate_id: str
    frozen_config: FrozenEvaluatorConfig
    candidate_fingerprint: str
    status: str = "completed"


class AnalyticsSnapshot(BaseModel):
    primary_metric_improvement: float
    guardrail_delta: float
    health_bonus: float
    confidence_bonus: float
    confidence: float
    srm_ok: bool
    data_quality_ok: bool


class FixedEvaluatorResult(BaseModel):
    score: float
    recommendation: DecisionRecommendation
    hard_fail_code: str | None = None
    score_breakdown: dict[str, float]
    simulation_run: SimulationRun
    analytics_snapshot: AnalyticsSnapshot


@dataclass(frozen=True)
class _SimulationPayload:
    primary_metric_improvement: float
    guardrail_delta: float
    confidence: float
    srm_ok: bool
    data_quality_ok: bool


def _fingerprint_candidate(candidate: CandidateConfig) -> str:
    payload = json.dumps(candidate.content, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def create_or_update_candidate_config(candidate: CandidateConfig) -> CandidateConfig:
    """Canonical evaluator-chain entrypoint for candidate materialization."""
    return candidate


def simulation_run(
    *,
    candidate: CandidateConfig,
    frozen_config: FrozenEvaluatorConfig,
) -> SimulationRun:
    return SimulationRun(
        run_id=f"simrun_{uuid4().hex}",
        candidate_id=candidate.candidate_id,
        frozen_config=frozen_config,
        candidate_fingerprint=_fingerprint_candidate(candidate),
    )


def _build_simulation_payload(*, run: SimulationRun) -> _SimulationPayload:
    seed_material = (
        f"{run.frozen_config.seed}:{run.candidate_fingerprint}:"
        f"{run.frozen_config.synthetic_user_budget}:{run.frozen_config.synthetic_event_budget}:"
        f"{run.frozen_config.runtime_window_minutes}:{','.join(run.frozen_config.segments)}"
    )
    rng = random.Random(seed_material)

    primary_metric_improvement = (rng.random() - 0.5) * 0.2
    guardrail_delta = (rng.random() - 0.5) * 0.16
    confidence = 0.80 + (rng.random() * 0.20)
    srm_ok = rng.random() >= 0.02
    data_quality_ok = rng.random() >= 0.02
    return _SimulationPayload(
        primary_metric_improvement=primary_metric_improvement,
        guardrail_delta=guardrail_delta,
        confidence=confidence,
        srm_ok=srm_ok,
        data_quality_ok=data_quality_ok,
    )


def simulation_status(*, run: SimulationRun) -> str:
    return run.status


def analytics_get(*, run: SimulationRun) -> AnalyticsSnapshot:
    payload = _build_simulation_payload(run=run)
    health_bonus = 0.05 if payload.guardrail_delta >= 0.0 else -0.05
    confidence_bonus = max((payload.confidence - 0.90) * 0.5, 0.0)
    return AnalyticsSnapshot(
        primary_metric_improvement=payload.primary_metric_improvement,
        guardrail_delta=payload.guardrail_delta,
        health_bonus=health_bonus,
        confidence_bonus=confidence_bonus,
        confidence=payload.confidence,
        srm_ok=payload.srm_ok,
        data_quality_ok=payload.data_quality_ok,
    )


def decision_summary_get(*, analytics: AnalyticsSnapshot) -> DecisionSummary:
    return get_decision_summary(guardrail_delta=analytics.guardrail_delta)


def evaluate_fixed_score(
    *,
    candidate: CandidateConfig,
    frozen_config: FrozenEvaluatorConfig,
) -> FixedEvaluatorResult:
    create_or_update_candidate_config(candidate)
    run = simulation_run(candidate=candidate, frozen_config=frozen_config)
    if simulation_status(run=run) != "completed":
        raise RuntimeError("Simulation run did not complete")

    analytics = analytics_get(run=run)
    decision_summary = decision_summary_get(analytics=analytics)

    if decision_summary.recommendation == DecisionRecommendation.ROLLBACK:
        return FixedEvaluatorResult(
            score=float("-inf"),
            recommendation=decision_summary.recommendation,
            hard_fail_code="ROLLBACK_RECOMMENDATION",
            score_breakdown={
                "normalized_primary_metric_improvement": 0.0,
                "health_bonus": 0.0,
                "confidence_bonus": 0.0,
                "complexity_penalty": 0.0,
            },
            simulation_run=run,
            analytics_snapshot=analytics,
        )

    if not analytics.srm_ok or not analytics.data_quality_ok:
        return FixedEvaluatorResult(
            score=float("-inf"),
            recommendation=decision_summary.recommendation,
            hard_fail_code="DATA_QUALITY_GATE_FAILED",
            score_breakdown={
                "normalized_primary_metric_improvement": 0.0,
                "health_bonus": 0.0,
                "confidence_bonus": 0.0,
                "complexity_penalty": 0.0,
            },
            simulation_run=run,
            analytics_snapshot=analytics,
        )

    complexity_penalty = min(candidate.complexity_score, 1.0) * 0.10
    score_breakdown = {
        "normalized_primary_metric_improvement": analytics.primary_metric_improvement,
        "health_bonus": analytics.health_bonus,
        "confidence_bonus": analytics.confidence_bonus,
        "complexity_penalty": complexity_penalty,
    }
    score = (
        score_breakdown["normalized_primary_metric_improvement"]
        + score_breakdown["health_bonus"]
        + score_breakdown["confidence_bonus"]
        - score_breakdown["complexity_penalty"]
    )

    return FixedEvaluatorResult(
        score=score,
        recommendation=decision_summary.recommendation,
        score_breakdown=score_breakdown,
        simulation_run=run,
        analytics_snapshot=analytics,
    )
