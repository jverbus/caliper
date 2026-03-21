from __future__ import annotations

import pytest
from caliper_storage.sqlalchemy_models import AuditRow
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api import dependencies
from apps.api.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.reset_dependency_caches()


def _job_payload(name: str = "Arm test") -> dict[str, object]:
    return {
        "workspace_id": "ws-demo",
        "name": name,
        "surface_type": "web",
        "objective_spec": {
            "reward_formula": "1.0 * signup",
            "penalties": [],
            "secondary_metrics": ["ctr"],
        },
        "guardrail_spec": {"rules": []},
        "policy_spec": {
            "policy_family": "fixed_split",
            "params": {"weights": [0.5, 0.5]},
            "update_cadence": {"mode": "periodic", "seconds": 300},
            "context_schema_version": None,
        },
        "segment_spec": {"dimensions": ["country"]},
        "schedule_spec": {"report_cron": "0 7 * * *"},
    }


def _arm_payload(count: int) -> dict[str, object]:
    return {
        "workspace_id": "ws-demo",
        "arms": [
            {
                "arm_id": f"arm_{idx:03d}",
                "name": f"Variant {idx}",
                "arm_type": "artifact",
                "payload_ref": f"s3://caliper/variant-{idx}.json",
                "metadata": {"priority": idx % 3, "locale": "en-US"},
            }
            for idx in range(count)
        ],
    }


def test_arm_batch_register_and_lifecycle_are_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    create_job = client.post("/v1/jobs", json=_job_payload())
    assert create_job.status_code == 200
    job_id = create_job.json()["job_id"]

    register_response = client.post(
        f"/v1/jobs/{job_id}/arms:batch_register",
        json=_arm_payload(120),
    )
    assert register_response.status_code == 200
    register_body = register_response.json()
    assert register_body["registered_count"] == 120
    assert len(register_body["arms"]) == 120
    assert register_body["arms"][0]["metadata"]["locale"] == "en-US"

    list_response = client.get(f"/v1/jobs/{job_id}/arms", params={"workspace_id": "ws-demo"})
    assert list_response.status_code == 200
    assert len(list_response.json()) == 120

    hold_response = client.post(
        f"/v1/jobs/{job_id}/arms/arm_000:lifecycle",
        json={"workspace_id": "ws-demo", "action": "hold"},
    )
    retire_response = client.post(
        f"/v1/jobs/{job_id}/arms/arm_001:lifecycle",
        json={"workspace_id": "ws-demo", "action": "retire"},
    )
    resume_response = client.post(
        f"/v1/jobs/{job_id}/arms/arm_000:lifecycle",
        json={"workspace_id": "ws-demo", "action": "resume"},
    )

    assert hold_response.status_code == 200
    assert hold_response.json()["state"] == "held_out"
    assert retire_response.status_code == 200
    assert retire_response.json()["state"] == "retired"
    assert resume_response.status_code == 200
    assert resume_response.json()["state"] == "active"

    session_factory = dependencies.get_session_factory()
    with session_factory() as session:
        audit_rows = list(
            session.scalars(
                select(AuditRow).where(AuditRow.job_id == job_id).order_by(AuditRow.audit_id.asc())
            ).all()
        )

    assert [row.action for row in audit_rows] == [
        "job.create",
        "arm.batch_register",
        "arm.hold",
        "arm.retire",
        "arm.resume",
    ]


def test_arm_endpoints_validate_workspace_and_missing_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    create_job = client.post("/v1/jobs", json=_job_payload())
    assert create_job.status_code == 200
    job_id = create_job.json()["job_id"]

    bad_workspace = client.post(
        f"/v1/jobs/{job_id}/arms:batch_register",
        json={"workspace_id": "ws-other", "arms": []},
    )
    assert bad_workspace.status_code == 400

    missing_arm = client.post(
        f"/v1/jobs/{job_id}/arms/arm_missing:lifecycle",
        json={"workspace_id": "ws-demo", "action": "hold"},
    )
    assert missing_arm.status_code == 404

    missing_job = client.post(
        "/v1/jobs/job_missing/arms:batch_register",
        json={"workspace_id": "ws-demo", "arms": []},
    )
    assert missing_job.status_code == 404
