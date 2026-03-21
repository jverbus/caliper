from __future__ import annotations

from caliper_core.decision import DecisionRecommendation

from apps.api.autotune_evaluator import (
    CandidateConfig,
    FrozenEvaluatorConfig,
    evaluate_fixed_score,
)


def test_same_candidate_and_seed_yields_same_score() -> None:
    candidate = CandidateConfig(
        candidate_id="cand-1",
        content={"prompt": "hello world"},
        complexity_score=0.15,
    )
    frozen = FrozenEvaluatorConfig(
        simulation_mode="deterministic",
        segments=("all",),
        synthetic_user_budget=1200,
        synthetic_event_budget=25000,
        seed=1337,
        runtime_window_minutes=30,
    )

    first = evaluate_fixed_score(candidate=candidate, frozen_config=frozen)
    second = evaluate_fixed_score(candidate=candidate, frozen_config=frozen)

    assert first.score == second.score
    assert first.score_breakdown == second.score_breakdown
    assert first.analytics_snapshot.model_dump() == second.analytics_snapshot.model_dump()


def test_different_seed_changes_score() -> None:
    candidate = CandidateConfig(
        candidate_id="cand-1",
        content={"prompt": "hello world"},
        complexity_score=0.15,
    )
    frozen_a = FrozenEvaluatorConfig(seed=1337)
    frozen_b = FrozenEvaluatorConfig(seed=1338)

    result_a = evaluate_fixed_score(candidate=candidate, frozen_config=frozen_a)
    result_b = evaluate_fixed_score(candidate=candidate, frozen_config=frozen_b)

    assert result_a.score != result_b.score


def test_guardrail_regression_forces_hard_fail_rollback() -> None:
    candidate = CandidateConfig(
        candidate_id="cand-regression",
        content={"prompt": "risky variant", "regression_bias": "high"},
    )

    rollback_result = None
    for seed in range(1, 500):
        result = evaluate_fixed_score(
            candidate=candidate,
            frozen_config=FrozenEvaluatorConfig(seed=seed),
        )
        if result.recommendation == DecisionRecommendation.ROLLBACK:
            rollback_result = result
            break

    assert rollback_result is not None
    assert rollback_result.hard_fail_code == "ROLLBACK_RECOMMENDATION"
    assert rollback_result.score == float("-inf")


def test_baseline_vs_candidate_uses_identical_frozen_budget() -> None:
    frozen = FrozenEvaluatorConfig(
        simulation_mode="deterministic",
        segments=("all", "new-users"),
        synthetic_user_budget=900,
        synthetic_event_budget=5000,
        seed=777,
        runtime_window_minutes=45,
    )
    baseline = CandidateConfig(
        candidate_id="baseline",
        content={"prompt": "baseline"},
        complexity_score=0.0,
    )
    candidate = CandidateConfig(
        candidate_id="candidate",
        content={"prompt": "candidate"},
        complexity_score=0.3,
    )

    baseline_result = evaluate_fixed_score(candidate=baseline, frozen_config=frozen)
    candidate_result = evaluate_fixed_score(candidate=candidate, frozen_config=frozen)

    assert baseline_result.simulation_run.frozen_config.model_dump() == frozen.model_dump()
    assert candidate_result.simulation_run.frozen_config.model_dump() == frozen.model_dump()
