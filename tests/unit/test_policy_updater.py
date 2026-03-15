from __future__ import annotations

from datetime import UTC, datetime

from caliper_core.models import (
    Arm,
    ArmType,
    GuardrailSpec,
    Job,
    ObjectiveSpec,
    PolicyFamily,
    PolicySpec,
    SurfaceType,
)
from caliper_policies.updater import PolicyUpdater
from caliper_reward.engine import RewardRecord


def _job(policy_family: PolicyFamily, params: dict[str, object]) -> Job:
    return Job(
        workspace_id="ws-demo",
        name="Updater fixture",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(reward_formula="conversion"),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(policy_family=policy_family, params=params),
    )


def _arms(job_id: str) -> list[Arm]:
    return [
        Arm(
            workspace_id="ws-demo",
            job_id=job_id,
            arm_id="arm-a",
            name="arm-a",
            arm_type=ArmType.ARTIFACT,
            payload_ref="web://arm-a",
            metadata={},
        ),
        Arm(
            workspace_id="ws-demo",
            job_id=job_id,
            arm_id="arm-b",
            name="arm-b",
            arm_type=ArmType.ARTIFACT,
            payload_ref="web://arm-b",
            metadata={},
        ),
    ]


def _record(arm_id: str, reward: float, normalized_reward: float) -> RewardRecord:
    return RewardRecord(
        workspace_id="ws-demo",
        job_id="job-1",
        decision_id=f"dec-{arm_id}-{reward}",
        unit_id=f"unit-{arm_id}-{reward}",
        arm_id=arm_id,
        propensity=0.5,
        reward=reward,
        normalized_reward=normalized_reward,
        observed_at=datetime.now(tz=UTC),
        metrics={"conversion": reward},
    )


def test_epsilon_greedy_update_accumulates_means_and_counts() -> None:
    updater = PolicyUpdater()
    job = _job(
        PolicyFamily.EPSILON_GREEDY,
        {
            "epsilon": 0.1,
            "value_estimates": {"arm-a": 0.5},
            "pull_counts": {"arm-a": 2},
            "policy_version": "v3",
        },
    ).model_copy(update={"job_id": "job-1"})

    result = updater.update(
        job=job,
        arms=_arms(job.job_id),
        records=[
            _record("arm-a", 1.0, 1.0),
            _record("arm-a", 0.0, 0.0),
            _record("arm-b", 0.8, 0.8),
        ],
    )

    assert result is not None
    assert result.record_count == 3
    assert result.updated_arm_ids == ("arm-a", "arm-b")
    assert result.params["epsilon"] == 0.1

    value_estimates = result.params["value_estimates"]
    pull_counts = result.params["pull_counts"]
    assert isinstance(value_estimates, dict)
    assert isinstance(pull_counts, dict)

    assert abs(float(value_estimates["arm-a"]) - 0.5) < 1e-9
    assert int(pull_counts["arm-a"]) == 4
    assert abs(float(value_estimates["arm-b"]) - 0.8) < 1e-9
    assert int(pull_counts["arm-b"]) == 1


def test_ucb1_update_accumulates_means_and_counts() -> None:
    updater = PolicyUpdater()
    job = _job(
        PolicyFamily.UCB1,
        {
            "mean_rewards": {"arm-a": 0.2, "arm-b": 0.6},
            "pull_counts": {"arm-a": 5, "arm-b": 5},
            "exploration_c": 1.0,
        },
    ).model_copy(update={"job_id": "job-1"})

    result = updater.update(
        job=job,
        arms=_arms(job.job_id),
        records=[
            _record("arm-a", 1.0, 1.0),
            _record("arm-b", 0.0, 0.0),
            _record("arm-b", 0.0, 0.0),
        ],
    )

    assert result is not None
    mean_rewards = result.params["mean_rewards"]
    pull_counts = result.params["pull_counts"]
    assert isinstance(mean_rewards, dict)
    assert isinstance(pull_counts, dict)

    assert abs(float(mean_rewards["arm-a"]) - (2.0 / 6.0)) < 1e-9
    assert int(pull_counts["arm-a"]) == 6
    assert abs(float(mean_rewards["arm-b"]) - (3.0 / 7.0)) < 1e-9
    assert int(pull_counts["arm-b"]) == 7


def test_thompson_sampling_update_uses_normalized_reward_mass() -> None:
    updater = PolicyUpdater()
    job = _job(
        PolicyFamily.THOMPSON_SAMPLING,
        {
            "alpha": {"arm-a": 2.0, "arm-b": 1.0},
            "beta": {"arm-a": 3.0, "arm-b": 1.0},
        },
    ).model_copy(update={"job_id": "job-1"})

    result = updater.update(
        job=job,
        arms=_arms(job.job_id),
        records=[
            _record("arm-a", 1.0, 1.0),
            _record("arm-a", 0.4, 0.25),
            _record("arm-b", 0.0, 0.0),
        ],
    )

    assert result is not None
    alpha = result.params["alpha"]
    beta = result.params["beta"]
    assert isinstance(alpha, dict)
    assert isinstance(beta, dict)

    assert abs(float(alpha["arm-a"]) - 3.25) < 1e-9
    assert abs(float(beta["arm-a"]) - 3.75) < 1e-9
    assert abs(float(alpha["arm-b"]) - 1.0) < 1e-9
    assert abs(float(beta["arm-b"]) - 2.0) < 1e-9
