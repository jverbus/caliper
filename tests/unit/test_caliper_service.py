from __future__ import annotations

from pathlib import Path

from caliper_core.models import (
    ArmBulkRegisterRequest,
    ArmInput,
    ArmType,
    AssignRequest,
    ExposureCreate,
    GuardrailSpec,
    Job,
    ObjectiveSpec,
    OutcomeCreate,
    OutcomeEvent,
    PolicyFamily,
    PolicySpec,
    ReportGenerateRequest,
    SurfaceType,
)
from caliper_sdk import CaliperService
from caliper_storage import SQLRepository, build_engine, init_db, make_session_factory


def _job() -> Job:
    return Job(
        workspace_id="ws-demo",
        name="Demo",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(reward_formula="signup"),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.FIXED_SPLIT,
            params={"weights": {"arm-a": 1.0}},
        ),
    )


def test_caliper_service_core_flow(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path}/service.db")
    init_db(engine)
    repository = SQLRepository(make_session_factory(engine))
    service = CaliperService(repository=repository)

    created = service.create_job(_job())
    registered = service.add_arms(
        job_id=created.job_id,
        payload=ArmBulkRegisterRequest(
            workspace_id=created.workspace_id,
            arms=[
                ArmInput(
                    arm_id="arm-a",
                    name="Arm A",
                    arm_type=ArmType.ARTIFACT,
                    payload_ref="file://arm-a",
                )
            ],
        ),
    )
    assert registered.registered_count == 1

    decision = service.assign(
        AssignRequest(
            workspace_id=created.workspace_id,
            job_id=created.job_id,
            unit_id="u1",
            idempotency_key="assign-1",
        )
    )

    exposure_payload = ExposureCreate(
        workspace_id=created.workspace_id,
        job_id=created.job_id,
        decision_id=decision.decision_id,
        unit_id="u1",
    )
    first_exposure = service.log_exposure(exposure_payload)
    second_exposure = service.log_exposure(exposure_payload)
    assert first_exposure == second_exposure

    outcome_payload = OutcomeCreate(
        workspace_id=created.workspace_id,
        job_id=created.job_id,
        decision_id=decision.decision_id,
        unit_id="u1",
        events=[OutcomeEvent(outcome_type="signup", value=1.0)],
    )
    first_outcome = service.log_outcome(outcome_payload)
    second_outcome = service.log_outcome(outcome_payload)
    assert first_outcome == second_outcome

    report = service.generate_report(
        job_id=created.job_id,
        payload=ReportGenerateRequest(workspace_id=created.workspace_id),
    )
    assert report.job_id == created.job_id
