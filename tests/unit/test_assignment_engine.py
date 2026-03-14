from __future__ import annotations

from collections import Counter

from caliper_core.models import (
    Arm,
    ArmInput,
    ArmState,
    ArmType,
    AssignRequest,
    GuardrailSpec,
    Job,
    ObjectiveSpec,
    PolicyFamily,
    PolicySpec,
    SurfaceType,
)
from caliper_policies.engine import AssignmentEngine


def _job() -> Job:
    return Job(
        workspace_id="ws_demo",
        name="job",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(reward_formula="1.0 * signup"),
        guardrail_spec=GuardrailSpec(),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.FIXED_SPLIT,
            params={"weights": {"arm_a": 0.8, "arm_b": 0.2, "arm_c": 0.0}},
        ),
    )


def _arm(arm_id: str, state: ArmState = ArmState.ACTIVE) -> Arm:
    arm_input = ArmInput(
        arm_id=arm_id,
        name=arm_id,
        arm_type=ArmType.ARTIFACT,
        payload_ref=f"file://{arm_id}",
    )
    return Arm(workspace_id="ws_demo", job_id="job_1", state=state, **arm_input.model_dump())


def test_fixed_split_respects_candidate_subset() -> None:
    engine = AssignmentEngine()
    job = _job().model_copy(update={"job_id": "job_1"})
    request = AssignRequest(
        workspace_id="ws_demo",
        job_id="job_1",
        unit_id="u1",
        candidate_arms=["arm_b", "arm_c"],
        idempotency_key="k1",
    )
    result = engine.assign(
        job=job,
        request=request,
        arms=[_arm("arm_a"), _arm("arm_b"), _arm("arm_c")],
    )
    assert result.arm_id == "arm_b"
    assert set(result.candidate_arms) == {"arm_b", "arm_c"}


def test_fixed_split_weighted_distribution_is_close() -> None:
    engine = AssignmentEngine()
    job = _job().model_copy(update={"job_id": "job_1"})
    arms = [_arm("arm_a"), _arm("arm_b")]

    counts: Counter[str] = Counter()
    for idx in range(2000):
        request = AssignRequest(
            workspace_id="ws_demo",
            job_id="job_1",
            unit_id=f"u{idx}",
            idempotency_key=f"req-{idx}",
        )
        result = engine.assign(job=job, request=request, arms=arms)
        counts[result.arm_id] += 1

    share_a = counts["arm_a"] / 2000
    assert 0.75 < share_a < 0.85


def test_fixed_split_falls_back_to_equal_weights_when_missing() -> None:
    engine = AssignmentEngine()
    job = _job().model_copy(
        update={
            "job_id": "job_1",
            "policy_spec": PolicySpec(policy_family=PolicyFamily.FIXED_SPLIT),
        }
    )
    request = AssignRequest(
        workspace_id="ws_demo",
        job_id="job_1",
        unit_id="u1",
        idempotency_key="k1",
    )
    result = engine.assign(job=job, request=request, arms=[_arm("arm_a"), _arm("arm_b")])
    assert result.diagnostics.scores == {"arm_a": 0.5, "arm_b": 0.5}
    assert result.propensity == 0.5
    assert result.diagnostics.fallback_used is True


def test_epsilon_greedy_prefers_better_arms_in_seeded_simulation() -> None:
    engine = AssignmentEngine()
    job = _job().model_copy(
        update={
            "job_id": "job_1",
            "policy_spec": PolicySpec(
                policy_family=PolicyFamily.EPSILON_GREEDY,
                params={
                    "epsilon": 0.1,
                    "value_estimates": {"arm_a": 0.8, "arm_b": 0.2},
                },
            ),
        }
    )
    arms = [_arm("arm_a"), _arm("arm_b")]

    counts: Counter[str] = Counter()
    for idx in range(2000):
        request = AssignRequest(
            workspace_id="ws_demo",
            job_id="job_1",
            unit_id=f"u{idx}",
            idempotency_key=f"req-{idx}",
        )
        result = engine.assign(job=job, request=request, arms=arms)
        counts[result.arm_id] += 1

    assert counts["arm_a"] > counts["arm_b"]
    assert 0.9 < (counts["arm_a"] / 2000) < 1.0


def test_epsilon_greedy_propensity_and_diagnostics_are_valid() -> None:
    engine = AssignmentEngine()
    job = _job().model_copy(
        update={
            "job_id": "job_1",
            "policy_spec": PolicySpec(
                policy_family=PolicyFamily.EPSILON_GREEDY,
                params={
                    "epsilon": 0.2,
                    "value_estimates": {"arm_a": 0.8, "arm_b": 0.2},
                },
            ),
        }
    )
    request = AssignRequest(
        workspace_id="ws_demo",
        job_id="job_1",
        unit_id="u42",
        idempotency_key="req-42",
    )

    result = engine.assign(job=job, request=request, arms=[_arm("arm_a"), _arm("arm_b")])

    assert result.diagnostics.reason == "epsilon_greedy_policy"
    assert result.diagnostics.scores == {"arm_a": 0.9, "arm_b": 0.1}
    assert 0.0 < result.propensity <= 1.0
    assert result.propensity == result.diagnostics.scores[result.arm_id]
