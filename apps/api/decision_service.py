from __future__ import annotations

from caliper_core.decision import DecisionRuleInput, DecisionSummary, evaluate_decision


def _build_decision_input(*, guardrail_regression: bool | None) -> DecisionRuleInput:
    return DecisionRuleInput(guardrail_regression=guardrail_regression)


def get_decision_summary(*, guardrail_regression: bool | None = None) -> DecisionSummary:
    decision_input = _build_decision_input(guardrail_regression=guardrail_regression)
    recommendation = evaluate_decision(decision_input)
    return DecisionSummary(recommendation=recommendation)
