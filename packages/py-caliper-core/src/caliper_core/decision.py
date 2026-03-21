from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class DecisionRecommendation(StrEnum):
    ROLLBACK = "ROLLBACK"
    HOLD = "HOLD"
    RAMP = "RAMP"
    SHIP = "SHIP"


class DecisionRuleInput(BaseModel):
    guardrail_regression: bool | None = None


class DecisionSummary(BaseModel):
    recommendation: DecisionRecommendation


def evaluate_decision(rule_input: DecisionRuleInput) -> DecisionRecommendation:
    if rule_input.guardrail_regression is True:
        return DecisionRecommendation.ROLLBACK
    if rule_input.guardrail_regression is None:
        return DecisionRecommendation.HOLD
    return DecisionRecommendation.SHIP
