from __future__ import annotations

from caliper_core.decision import DecisionRecommendation

from apps.api.decision_service import get_decision_summary


def test_guardrail_regression_true_returns_rollback() -> None:
    summary = get_decision_summary(guardrail_regression=True)

    assert summary.recommendation == DecisionRecommendation.ROLLBACK


def test_guardrail_regression_none_blocks_ramp_or_ship_with_hold() -> None:
    summary = get_decision_summary(guardrail_regression=None)

    assert summary.recommendation == DecisionRecommendation.HOLD


def test_computed_guardrail_regression_returns_rollback() -> None:
    summary = get_decision_summary(
        guardrail_regression=None,
        guardrail_delta=-0.08,
        max_guardrail_drop=0.05,
    )

    assert summary.recommendation == DecisionRecommendation.ROLLBACK


def test_decision_service_supports_policy_threshold_simulation() -> None:
    summary = get_decision_summary(
        guardrail_regression=False,
        confidence=0.93,
        confidence_threshold=0.92,
        policy_version="sim-v2",
    )

    assert summary.recommendation == DecisionRecommendation.RAMP
