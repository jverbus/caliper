from __future__ import annotations

import pytest
from api import dependencies
from api.main import create_app
from caliper_storage import SQLRepository
from fastapi.testclient import TestClient


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


def _job_payload() -> dict[str, object]:
    return {
        "workspace_id": "ws-demo",
        "name": "Assign job",
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
            "params": {"weights": {"arm-a": 0.8, "arm-b": 0.2}},
            "update_cadence": {"mode": "periodic", "seconds": 300},
            "context_schema_version": None,
        },
        "segment_spec": {"dimensions": ["country"]},
        "schedule_spec": {"report_cron": "0 7 * * *"},
    }


def _register_arms(client: TestClient, job_id: str) -> None:
    register_resp = client.post(
        f"/v1/jobs/{job_id}/arms:batch_register",
        json={
            "workspace_id": "ws-demo",
            "arms": [
                {
                    "arm_id": "arm-a",
                    "name": "A",
                    "arm_type": "artifact",
                    "payload_ref": "file://a",
                    "metadata": {},
                },
                {
                    "arm_id": "arm-b",
                    "name": "B",
                    "arm_type": "artifact",
                    "payload_ref": "file://b",
                    "metadata": {},
                },
            ],
        },
    )
    assert register_resp.status_code == 200


def test_assign_is_idempotent_and_persists_decision_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]
    _register_arms(client, job_id)

    payload = {
        "workspace_id": "ws-demo",
        "job_id": job_id,
        "unit_id": "visitor-1",
        "candidate_arms": ["arm-a"],
        "context": {"country": "US"},
        "idempotency_key": "req-1",
    }

    first = client.post("/v1/assign", json=payload)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["arm_id"] == "arm-a"

    second = client.post("/v1/assign", json=payload)
    assert second.status_code == 200
    assert second.json() == first_body

    repository = SQLRepository(dependencies.get_session_factory())
    decision = repository.get_decision(first_body["decision_id"])
    assert decision is not None
    assert decision.arm_id == "arm-a"

    events = repository.replay(workspace_id="ws-demo", job_id=job_id)
    assigned = [event for event in events if event.event_type == "decision.assigned"]
    assert len(assigned) == 1
    assert assigned[0].entity_id == first_body["decision_id"]


def test_assign_rejects_reused_idempotency_key_with_different_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]
    _register_arms(client, job_id)

    first = client.post(
        "/v1/assign",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "unit_id": "visitor-1",
            "candidate_arms": ["arm-a"],
            "context": {},
            "idempotency_key": "req-shared",
        },
    )
    assert first.status_code == 200

    conflict = client.post(
        "/v1/assign",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "unit_id": "visitor-2",
            "candidate_arms": ["arm-b"],
            "context": {},
            "idempotency_key": "req-shared",
        },
    )
    assert conflict.status_code == 409


def test_assign_candidate_subset_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]
    _register_arms(client, job_id)

    response = client.post(
        "/v1/assign",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "unit_id": "visitor-subset",
            "candidate_arms": ["arm-b"],
            "context": {"country": "CA"},
            "idempotency_key": "req-subset",
        },
    )
    assert response.status_code == 200
    assert response.json()["arm_id"] == "arm-b"
