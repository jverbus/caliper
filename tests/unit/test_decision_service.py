from __future__ import annotations

from apps.api.decision_service import get_decision_summary
from caliper_core.decision import DecisionRecommendation


def test_guardrail_regression_true_returns_rollback() -> None:
    summary = get_decision_summary(guardrail_regression=True)

    assert summary.recommendation == DecisionRecommendation.ROLLBACK


def test_guardrail_regression_none_blocks_ramp_or_ship_with_hold() -> None:
    summary = get_decision_summary(guardrail_regression=None)

    assert summary.recommendation == DecisionRecommendation.HOLD
