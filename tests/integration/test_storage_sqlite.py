from __future__ import annotations

from caliper_core.models import (
    Arm,
    ArmType,
    AssignResult,
    ExposureCreate,
    GuardrailSpec,
    Job,
    ObjectiveSpec,
    OutcomeCreate,
    OutcomeEvent,
    PolicyFamily,
    PolicySpec,
    SurfaceType,
)
from caliper_storage.engine import build_engine, init_db, make_session_factory
from caliper_storage.repositories import SQLiteRepository


def build_repo() -> SQLiteRepository:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return SQLiteRepository(make_session_factory(engine))


def test_sqlite_job_arm_decision_exposure_outcome_roundtrip() -> None:
    repo = build_repo()

    job = Job(
        workspace_id="ws-1",
        name="Homepage ranking",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(reward_formula="click"),
        guardrail_spec=GuardrailSpec(),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.FIXED_SPLIT,
            params={"weights": [0.5, 0.5]},
        ),
    )
    persisted_job = repo.create_job(job)

    loaded_job = repo.get_job(persisted_job.job_id)
    assert loaded_job is not None
    assert loaded_job.job_id == persisted_job.job_id
    assert loaded_job.workspace_id == "ws-1"

    arm = Arm(
        arm_id="arm-a",
        workspace_id="ws-1",
        job_id=persisted_job.job_id,
        name="Variant A",
        arm_type=ArmType.ARTIFACT,
        payload_ref="s3://bucket/a.json",
        metadata={"color": "blue"},
    )
    repo.upsert_arm(arm)
    listed_arms = repo.list_arms("ws-1", persisted_job.job_id)
    assert len(listed_arms) == 1
    assert listed_arms[0].arm_id == "arm-a"

    decision = AssignResult(
        workspace_id="ws-1",
        job_id=persisted_job.job_id,
        unit_id="user-123",
        arm_id="arm-a",
        propensity=0.5,
        policy_family=PolicyFamily.FIXED_SPLIT,
        policy_version="v1",
        candidate_arms=["arm-a", "arm-b"],
    )
    repo.create_decision(decision)

    loaded_decision = repo.get_decision(decision.decision_id)
    assert loaded_decision is not None
    assert loaded_decision.unit_id == "user-123"

    exposure = ExposureCreate(
        workspace_id="ws-1",
        job_id=persisted_job.job_id,
        decision_id=decision.decision_id,
        unit_id="user-123",
        metadata={"placement": "hero"},
    )
    repo.create_exposure(exposure)
    exposures = repo.list_exposures("ws-1", persisted_job.job_id)
    assert len(exposures) == 1
    assert exposures[0].decision_id == decision.decision_id

    outcome = OutcomeCreate(
        workspace_id="ws-1",
        job_id=persisted_job.job_id,
        decision_id=decision.decision_id,
        unit_id="user-123",
        events=[OutcomeEvent(outcome_type="click", value=1.0)],
        metadata={"source": "test"},
    )
    repo.create_outcome(outcome)
    outcomes = repo.list_outcomes("ws-1", persisted_job.job_id)
    assert len(outcomes) == 1
    assert outcomes[0].events[0].outcome_type == "click"
