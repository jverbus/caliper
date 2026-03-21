from __future__ import annotations

from caliper_core.decision import (
    DecisionPolicyConfig,
    DecisionRecommendation,
    DecisionRuleInput,
    evaluate_decision,
)


def test_default_policy_thresholds_match_v2_spec_floor() -> None:
    policy = DecisionPolicyConfig()
    assert policy.ship_threshold == 0.95
    assert policy.ramp_threshold == 0.90


def test_default_behavior_is_preserved_when_confidence_missing() -> None:
    recommendation = evaluate_decision(
        DecisionRuleInput(guardrail_regression=False),
    )
    assert recommendation == DecisionRecommendation.SHIP


def test_alternate_policy_enables_simulation_of_ramp_and_ship_cutoffs() -> None:
    policy = DecisionPolicyConfig(version="sim-v2", confidence_threshold=0.92)

    hold = evaluate_decision(
        DecisionRuleInput(guardrail_regression=False, confidence=0.91, policy=policy)
    )
    ramp = evaluate_decision(
        DecisionRuleInput(guardrail_regression=False, confidence=0.93, policy=policy)
    )
    ship = evaluate_decision(
        DecisionRuleInput(guardrail_regression=False, confidence=0.96, policy=policy)
    )

    assert hold == DecisionRecommendation.HOLD
    assert ramp == DecisionRecommendation.RAMP
    assert ship == DecisionRecommendation.SHIP
