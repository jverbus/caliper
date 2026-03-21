from __future__ import annotations

from typing import Any, cast

import pytest
from caliper_storage import SQLRepository
from fastapi.testclient import TestClient

from apps.api import dependencies
from apps.api.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.reset_dependency_caches()


def _job_payload() -> dict[str, object]:
    return {
        "workspace_id": "ws-demo",
        "name": "Exposure job",
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
            "params": {"weights": {"arm-a": 1.0}},
            "update_cadence": {"mode": "periodic", "seconds": 300},
            "context_schema_version": None,
        },
        "segment_spec": {"dimensions": ["country"]},
        "schedule_spec": {"report_cron": "0 7 * * *"},
    }


def _register_arm(client: TestClient, job_id: str) -> None:
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
                }
            ],
        },
    )
    assert register_resp.status_code == 200


def _create_decision(client: TestClient, job_id: str) -> dict[str, Any]:
    assign = client.post(
        "/v1/assign",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "unit_id": "visitor-1",
            "candidate_arms": ["arm-a"],
            "context": {"country": "US"},
            "idempotency_key": f"assign-exposure-{job_id}",
        },
    )
    assert assign.status_code == 200
    return cast(dict[str, Any], assign.json())


def test_exposure_ingest_persists_event_and_is_duplicate_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]
    _register_arm(client, job_id)
    decision = _create_decision(client, job_id)

    payload = {
        "workspace_id": "ws-demo",
        "job_id": job_id,
        "decision_id": decision["decision_id"],
        "unit_id": "visitor-1",
        "exposure_type": "rendered",
        "timestamp": "2026-03-14T16:45:00Z",
        "metadata": {"page": "/pricing", "http_status": 200},
    }

    first = client.post("/v1/exposures", json=payload)
    assert first.status_code == 200

    duplicate = client.post("/v1/exposures", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()

    repository = SQLRepository(dependencies.get_session_factory())
    exposures = repository.list_exposures(workspace_id="ws-demo", job_id=job_id)
    assert len(exposures) == 1
    assert exposures[0].decision_id == decision["decision_id"]

    events = repository.replay(workspace_id="ws-demo", job_id=job_id)
    exposed = [event for event in events if event.event_type == "decision.exposed"]
    assert len(exposed) == 1
    assert exposed[0].entity_id == decision["decision_id"]


def test_exposure_requires_matching_decision_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]
    _register_arm(client, job_id)
    decision = _create_decision(client, job_id)

    mismatched = client.post(
        "/v1/exposures",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "decision_id": decision["decision_id"],
            "unit_id": "visitor-2",
            "exposure_type": "rendered",
            "timestamp": "2026-03-14T16:45:00Z",
            "metadata": {},
        },
    )
    assert mismatched.status_code == 400


def test_exposure_rejects_unknown_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]

    missing = client.post(
        "/v1/exposures",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "decision_id": "dec_missing",
            "unit_id": "visitor-1",
            "exposure_type": "rendered",
            "timestamp": "2026-03-14T16:45:00Z",
            "metadata": {},
        },
    )
    assert missing.status_code == 404
