from __future__ import annotations

from typing import Any, ClassVar

import pytest
from caliper_core.models import (
    ArmBulkRegisterRequest,
    ArmInput,
    ArmType,
    AssignRequest,
    ExposureCreate,
    Job,
    ObjectiveSpec,
    OutcomeCreate,
    OutcomeEvent,
    PolicyFamily,
    PolicySpec,
    ReportGenerateRequest,
    SurfaceType,
)
from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient


class _FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


class _FakeClient:
    requests: ClassVar[list[tuple[str, str, dict[str, Any] | None]]] = []

    def __init__(self, **_: object) -> None:
        self._responses: dict[tuple[str, str], dict[str, Any]] = {
            ("POST", "/v1/jobs"): {
                "job_id": "job_1",
                "status": "draft",
                "created_at": "2026-03-14T00:00:00Z",
            },
            ("GET", "/v1/jobs/job_1"): {
                "workspace_id": "ws-demo",
                "job_id": "job_1",
                "name": "Demo",
                "surface_type": "web",
                "objective_spec": {
                    "reward_formula": "signup",
                    "penalties": [],
                    "secondary_metrics": [],
                },
                "guardrail_spec": {"rules": []},
                "policy_spec": {
                    "policy_family": "fixed_split",
                    "params": {},
                    "update_cadence": {"mode": "periodic", "seconds": None},
                    "context_schema_version": None,
                },
                "segment_spec": {"dimensions": []},
                "schedule_spec": {"report_cron": None},
                "status": "draft",
                "approval_state": "not_required",
                "created_at": "2026-03-14T00:00:00Z",
                "updated_at": "2026-03-14T00:00:00Z",
            },
            ("POST", "/v1/jobs/job_1/arms:batch_register"): {
                "workspace_id": "ws-demo",
                "job_id": "job_1",
                "registered_count": 1,
                "arms": [],
            },
            ("POST", "/v1/assign"): {
                "decision_id": "dec_1",
                "workspace_id": "ws-demo",
                "job_id": "job_1",
                "unit_id": "u1",
                "arm_id": "arm-a",
                "propensity": 1.0,
                "policy_family": "fixed_split",
                "policy_version": "1",
                "context_schema_version": None,
                "diagnostics": {
                    "scores": {"arm-a": 1.0},
                    "reason": "fixed_split_weighted_draw",
                    "fallback_used": False,
                },
                "candidate_arms": ["arm-a"],
                "context": {},
                "timestamp": "2026-03-14T00:00:00Z",
            },
            ("POST", "/v1/exposures"): {
                "workspace_id": "ws-demo",
                "job_id": "job_1",
                "decision_id": "dec_1",
                "unit_id": "u1",
                "exposure_type": "rendered",
                "timestamp": "2026-03-14T00:00:00Z",
                "metadata": {},
            },
            ("POST", "/v1/outcomes"): {
                "workspace_id": "ws-demo",
                "job_id": "job_1",
                "decision_id": "dec_1",
                "unit_id": "u1",
                "events": [
                    {"outcome_type": "signup", "value": 1.0, "timestamp": "2026-03-14T00:00:00Z"}
                ],
                "attribution_window": {"hours": 24},
                "metadata": {},
            },
            ("POST", "/v1/jobs/job_1/reports:generate"): {
                "report_id": "r1",
                "workspace_id": "ws-demo",
                "job_id": "job_1",
                "generated_at": "2026-03-14T00:00:00Z",
                "leaders": [],
                "traffic_shifts": [],
                "guardrails": [],
                "segment_findings": [],
                "recommendations": [],
                "markdown": "# report",
                "html": "<html></html>",
            },
        }

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def request(self, method: str, path: str, json: dict[str, Any] | None = None) -> _FakeResponse:
        self.requests.append((method, path, json))
        return _FakeResponse(self._responses[(method, path)])


def _job() -> Job:
    return Job(
        workspace_id="ws-demo",
        name="Demo",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(reward_formula="signup"),
        guardrail_spec={"rules": []},
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.FIXED_SPLIT, params={"weights": {"arm-a": 1.0}}
        ),
    )


def test_service_client_core_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.requests.clear()
    monkeypatch.setattr("caliper_sdk.client.httpx.Client", _FakeClient)

    client = ServiceCaliperClient(api_url="http://localhost:8000")
    created = client.create_job(_job())
    assert created["job_id"] == "job_1"

    fetched = client.get_job(job_id="job_1")
    assert fetched.job_id == "job_1"

    registered = client.add_arms(
        job_id="job_1",
        payload=ArmBulkRegisterRequest(
            workspace_id="ws-demo",
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

    decision = client.assign(
        AssignRequest(
            workspace_id="ws-demo",
            job_id="job_1",
            unit_id="u1",
            idempotency_key="req-1",
        )
    )
    assert decision.arm_id == "arm-a"

    exposure = client.log_exposure(
        ExposureCreate(
            workspace_id="ws-demo",
            job_id="job_1",
            decision_id=decision.decision_id,
            unit_id="u1",
        )
    )
    assert exposure.decision_id == decision.decision_id

    outcome = client.log_outcome(
        OutcomeCreate(
            workspace_id="ws-demo",
            job_id="job_1",
            decision_id=decision.decision_id,
            unit_id="u1",
            events=[OutcomeEvent(outcome_type="signup", value=1.0)],
        )
    )
    assert outcome.events[0].outcome_type == "signup"

    report = client.generate_report(
        job_id="job_1",
        payload=ReportGenerateRequest(workspace_id="ws-demo"),
    )
    assert report.report_id == "r1"
    assert len(_FakeClient.requests) == 7


def test_embedded_client_core_flow(tmp_path: Any) -> None:
    client = EmbeddedCaliperClient(db_url=f"sqlite:///{tmp_path}/sdk.db")
    job = client.create_job(_job())

    registered = client.add_arms(
        job_id=job.job_id,
        payload=ArmBulkRegisterRequest(
            workspace_id=job.workspace_id,
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

    decision = client.assign(
        AssignRequest(
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            unit_id="u1",
            idempotency_key="assign-1",
        )
    )
    assert decision.arm_id == "arm-a"

    client.log_exposure(
        ExposureCreate(
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            decision_id=decision.decision_id,
            unit_id="u1",
        )
    )
    client.log_outcome(
        OutcomeCreate(
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            decision_id=decision.decision_id,
            unit_id="u1",
            events=[OutcomeEvent(outcome_type="signup", value=1.0)],
        )
    )
    report = client.generate_report(
        job_id=job.job_id,
        payload=ReportGenerateRequest(workspace_id=job.workspace_id),
    )
    assert report.job_id == job.job_id
