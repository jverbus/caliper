from __future__ import annotations

from caliper_core.decision import (
    DecisionPolicyConfig,
    DecisionRuleInput,
    DecisionSummary,
    evaluate_decision,
)


def _compute_guardrail_regression(
    *,
    guardrail_delta: float | None,
    max_guardrail_drop: float,
) -> bool | None:
    if guardrail_delta is None:
        return None
    return guardrail_delta < (0.0 - max_guardrail_drop)


def _build_decision_input(
    *,
    guardrail_regression: bool | None,
    guardrail_delta: float | None,
    max_guardrail_drop: float,
    confidence: float | None,
    confidence_threshold: float,
    policy_version: str,
) -> DecisionRuleInput:
    computed_regression = guardrail_regression
    if computed_regression is None:
        computed_regression = _compute_guardrail_regression(
            guardrail_delta=guardrail_delta,
            max_guardrail_drop=max_guardrail_drop,
        )
    return DecisionRuleInput(
        guardrail_regression=computed_regression,
        confidence=confidence,
        policy=DecisionPolicyConfig(
            version=policy_version,
            confidence_threshold=confidence_threshold,
        ),
    )


def get_decision_summary(
    *,
    guardrail_regression: bool | None = None,
    guardrail_delta: float | None = None,
    max_guardrail_drop: float = 0.05,
    confidence: float | None = None,
    confidence_threshold: float = 0.0,
    policy_version: str = "v1",
) -> DecisionSummary:
    decision_input = _build_decision_input(
        guardrail_regression=guardrail_regression,
        guardrail_delta=guardrail_delta,
        max_guardrail_drop=max_guardrail_drop,
        confidence=confidence,
        confidence_threshold=confidence_threshold,
        policy_version=policy_version,
    )
    recommendation = evaluate_decision(decision_input)
    return DecisionSummary(recommendation=recommendation)
