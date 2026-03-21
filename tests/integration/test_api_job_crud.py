from __future__ import annotations

import pytest
from caliper_storage.sqlalchemy_models import AuditRow
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api import dependencies
from apps.api.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.reset_dependency_caches()


def _job_payload(name: str = "Landing test") -> dict[str, object]:
    return {
        "workspace_id": "ws-demo",
        "name": name,
        "surface_type": "web",
        "objective_spec": {
            "reward_formula": "1.0 * signup",
            "penalties": ["0.05 * token_cost_usd"],
            "secondary_metrics": ["ctr"],
        },
        "guardrail_spec": {
            "rules": [
                {
                    "metric": "error_rate",
                    "op": "<",
                    "threshold": 0.01,
                    "action": "pause",
                }
            ]
        },
        "policy_spec": {
            "policy_family": "fixed_split",
            "params": {"weights": [0.5, 0.5]},
            "update_cadence": {"mode": "periodic", "seconds": 300},
            "context_schema_version": None,
        },
        "segment_spec": {"dimensions": ["country"]},
        "schedule_spec": {"report_cron": "0 7 * * *"},
    }


def test_job_crud_contract_and_audit_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    create_response = client.post("/v1/jobs", json=_job_payload())
    assert create_response.status_code == 200

    create_body = create_response.json()
    assert create_body["job_id"].startswith("job_")
    assert create_body["status"] == "draft"
    assert "created_at" in create_body

    job_id = create_body["job_id"]

    list_response = client.get("/v1/jobs")
    assert list_response.status_code == 200
    listed_jobs = list_response.json()
    assert job_id in [job["job_id"] for job in listed_jobs]

    filtered_list_response = client.get("/v1/jobs", params={"workspace_id": "ws-demo"})
    assert filtered_list_response.status_code == 200
    filtered_jobs = filtered_list_response.json()
    assert job_id in [job["job_id"] for job in filtered_jobs]

    get_response = client.get(f"/v1/jobs/{job_id}")
    assert get_response.status_code == 200
    get_body = get_response.json()
    assert get_body["job_id"] == job_id
    assert get_body["name"] == "Landing test"

    patch_response = client.patch(
        f"/v1/jobs/{job_id}",
        json={"name": "Landing test v2", "schedule_spec": {"report_cron": "15 8 * * *"}},
    )
    assert patch_response.status_code == 200
    patch_body = patch_response.json()
    assert patch_body["name"] == "Landing test v2"
    assert patch_body["schedule_spec"]["report_cron"] == "15 8 * * *"

    session_factory = dependencies.get_session_factory()
    with session_factory() as session:
        audit_rows = list(
            session.scalars(
                select(AuditRow).where(AuditRow.job_id == job_id).order_by(AuditRow.audit_id.asc())
            ).all()
        )

    assert [row.action for row in audit_rows] == ["job.create", "job.update"]
    assert audit_rows[0].metadata_json == {"status": "draft"}
    assert audit_rows[1].metadata_json == {"patched_fields": ["name", "schedule_spec"]}


def test_job_endpoints_return_404_for_unknown_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    get_missing = client.get("/v1/jobs/job_missing")
    patch_missing = client.patch("/v1/jobs/job_missing", json={"name": "does-not-matter"})

    assert get_missing.status_code == 404
    assert patch_missing.status_code == 404
