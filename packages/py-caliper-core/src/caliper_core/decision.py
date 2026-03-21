from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DecisionRecommendation(StrEnum):
    ROLLBACK = "ROLLBACK"
    HOLD = "HOLD"
    RAMP = "RAMP"
    SHIP = "SHIP"


class DecisionPolicyConfig(BaseModel):
    version: str = "v1"
    confidence_threshold: float = 0.0
    min_ship_threshold: float = 0.95
    min_ramp_threshold: float = 0.90

    @property
    def ship_threshold(self) -> float:
        return max(self.confidence_threshold, self.min_ship_threshold)

    @property
    def ramp_threshold(self) -> float:
        return max(self.confidence_threshold, self.min_ramp_threshold)


class DecisionRuleInput(BaseModel):
    guardrail_regression: bool | None = None
    confidence: float | None = None
    policy: DecisionPolicyConfig = Field(default_factory=DecisionPolicyConfig)


class DecisionSummary(BaseModel):
    recommendation: DecisionRecommendation


def evaluate_decision(rule_input: DecisionRuleInput) -> DecisionRecommendation:
    if rule_input.guardrail_regression is True:
        return DecisionRecommendation.ROLLBACK
    if rule_input.guardrail_regression is None:
        return DecisionRecommendation.HOLD

    if rule_input.confidence is None:
        return DecisionRecommendation.SHIP

    if rule_input.confidence >= rule_input.policy.ship_threshold:
        return DecisionRecommendation.SHIP
    if rule_input.confidence >= rule_input.policy.ramp_threshold:
        return DecisionRecommendation.RAMP
    return DecisionRecommendation.HOLD
