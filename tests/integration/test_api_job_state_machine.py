from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api import dependencies
from apps.api.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


def _job_payload(name: str = "Stateful job") -> dict[str, object]:
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


def test_job_state_transitions_and_audit_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]

    patch_resp = client.patch(f"/v1/jobs/{job_id}", json={"name": "Stateful v2"})
    assert patch_resp.status_code == 200

    activate_resp = client.post(
        f"/v1/jobs/{job_id}/resume",
        json={"workspace_id": "ws-demo", "approval_state": "approved"},
    )
    assert activate_resp.status_code == 200
    assert activate_resp.json()["status"] == "active"

    pause_resp = client.post(
        f"/v1/jobs/{job_id}/pause",
        json={"workspace_id": "ws-demo", "approval_state": "pending"},
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"
    assert pause_resp.json()["approval_state"] == "pending"

    # pause is non-destructive: prior mutable fields remain intact
    paused_job = client.get(f"/v1/jobs/{job_id}").json()
    assert paused_job["name"] == "Stateful v2"
    assert paused_job["policy_spec"]["policy_family"] == "fixed_split"

    resume_resp = client.post(
        f"/v1/jobs/{job_id}/resume",
        json={"workspace_id": "ws-demo", "approval_state": "approved"},
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "active"
    assert resume_resp.json()["approval_state"] == "approved"

    archive_resp = client.post(
        f"/v1/jobs/{job_id}/archive",
        json={"workspace_id": "ws-demo"},
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["status"] == "archived"

    audit_resp = client.get(f"/v1/jobs/{job_id}/audit", params={"workspace_id": "ws-demo"})
    assert audit_resp.status_code == 200
    actions = [entry["action"] for entry in audit_resp.json()]
    assert actions == [
        "job.create",
        "job.update",
        "job.resume",
        "job.pause",
        "job.resume",
        "job.archive",
    ]


def test_invalid_job_transition_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload(name="Invalid transitions")).json()
    job_id = created["job_id"]

    # draft -> paused is not allowed in the transition graph
    invalid_resp = client.post(
        f"/v1/jobs/{job_id}/pause",
        json={"workspace_id": "ws-demo", "approval_state": "pending"},
    )
    assert invalid_resp.status_code == 409


def test_resume_defaults_to_approved_when_unspecified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload(name="Resume default")).json()
    job_id = created["job_id"]

    activate_resp = client.post(
        f"/v1/jobs/{job_id}/resume",
        json={"workspace_id": "ws-demo"},
    )
    assert activate_resp.status_code == 200
    assert activate_resp.json()["status"] == "active"
    assert activate_resp.json()["approval_state"] == "approved"
