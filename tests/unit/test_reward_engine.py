from __future__ import annotations

from datetime import UTC, datetime, timedelta

from caliper_core.models import (
    AssignResult,
    AttributionWindow,
    DecisionDiagnostics,
    ObjectiveSpec,
    OutcomeCreate,
    OutcomeEvent,
    PolicyFamily,
)
from caliper_reward import RewardEngine


def _decision(*, decision_id: str, arm_id: str, timestamp: datetime) -> AssignResult:
    return AssignResult(
        decision_id=decision_id,
        workspace_id="ws_demo",
        job_id="job_demo",
        unit_id=f"unit-{decision_id}",
        arm_id=arm_id,
        propensity=0.5,
        policy_family=PolicyFamily.FIXED_SPLIT,
        policy_version="v1",
        diagnostics=DecisionDiagnostics(reason="test"),
        timestamp=timestamp,
    )


def _outcome(
    *,
    decision_id: str,
    unit_id: str,
    at: datetime,
    conversion: float,
    cost: float,
    latency_ms: float,
    window_hours: int = 24,
) -> OutcomeCreate:
    return OutcomeCreate(
        workspace_id="ws_demo",
        job_id="job_demo",
        decision_id=decision_id,
        unit_id=unit_id,
        events=[
            OutcomeEvent(outcome_type="conversion", value=conversion, timestamp=at),
            OutcomeEvent(outcome_type="cost", value=cost, timestamp=at),
            OutcomeEvent(outcome_type="latency_ms", value=latency_ms, timestamp=at),
        ],
        attribution_window=AttributionWindow(hours=window_hours),
    )


def test_reward_formula_is_reproducible_from_fixture_values() -> None:
    engine = RewardEngine()
    objective = ObjectiveSpec(
        reward_formula="(10 * conversion) - cost - (latency_ms / 1000)",
        penalties=["cost - 2"],
    )

    outcome = _outcome(
        decision_id="dec_1",
        unit_id="unit-dec_1",
        at=datetime(2026, 3, 14, 16, 0, tzinfo=UTC),
        conversion=1,
        cost=3,
        latency_ms=500,
    )

    reward, metrics = engine.evaluate_reward(objective_spec=objective, outcome=outcome)

    assert metrics == {"conversion": 1.0, "cost": 3.0, "latency_ms": 500.0}
    # base = 10 - 3 - 0.5 = 6.5 ; penalty = 1.0 => 5.5
    assert reward == 5.5


def test_policy_update_dataset_normalizes_rewards_and_filters_window() -> None:
    engine = RewardEngine()
    start = datetime(2026, 3, 14, 15, 0, tzinfo=UTC)
    decisions = [
        _decision(decision_id="dec_a", arm_id="arm_a", timestamp=start),
        _decision(decision_id="dec_b", arm_id="arm_b", timestamp=start + timedelta(minutes=5)),
    ]
    outcomes = [
        _outcome(
            decision_id="dec_a",
            unit_id="unit-dec_a",
            at=start + timedelta(minutes=30),
            conversion=1,
            cost=1,
            latency_ms=200,
        ),
        _outcome(
            decision_id="dec_b",
            unit_id="unit-dec_b",
            at=start + timedelta(hours=30),
            conversion=1,
            cost=0,
            latency_ms=100,
            window_hours=24,
        ),
    ]

    objective = ObjectiveSpec(reward_formula="(5 * conversion) - cost - (latency_ms / 1000)")

    dataset = engine.build_policy_update_dataset(
        objective_spec=objective,
        decisions=decisions,
        outcomes=outcomes,
    )

    assert len(dataset) == 1
    record = dataset[0]
    assert record.decision_id == "dec_a"
    assert record.reward == 3.8
    assert record.normalized_reward == 1.0
    assert record.metrics["cost"] == 1.0
