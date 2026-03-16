from __future__ import annotations

from uuid import uuid4

import pytest
from caliper_storage import SQLRepository
from fastapi.testclient import TestClient

from apps.api import dependencies
from apps.api.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


def _job_payload(
    *,
    workspace_id: str,
    context_schema_version: str | None = None,
    context_schemas: dict[str, object] | None = None,
) -> dict[str, object]:
    params: dict[str, object] = {"weights": {"arm-a": 0.8, "arm-b": 0.2}}
    if context_schemas is not None:
        params["context_schemas"] = context_schemas

    return {
        "workspace_id": workspace_id,
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
            "params": params,
            "update_cadence": {"mode": "periodic", "seconds": 300},
            "context_schema_version": context_schema_version,
        },
        "segment_spec": {"dimensions": ["country"]},
        "schedule_spec": {"report_cron": "0 7 * * *"},
    }


def _register_arms(client: TestClient, workspace_id: str, job_id: str) -> None:
    register_resp = client.post(
        f"/v1/jobs/{job_id}/arms:batch_register",
        json={
            "workspace_id": workspace_id,
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

    workspace_id = f"ws-{uuid4().hex[:8]}"
    created = client.post("/v1/jobs", json=_job_payload(workspace_id=workspace_id)).json()
    job_id = created["job_id"]
    _register_arms(client, workspace_id, job_id)

    payload = {
        "workspace_id": workspace_id,
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

    events = repository.replay(workspace_id=workspace_id, job_id=job_id)
    assigned = [event for event in events if event.event_type == "decision.assigned"]
    assert len(assigned) == 1
    assert assigned[0].entity_id == first_body["decision_id"]


def test_assign_rejects_reused_idempotency_key_with_different_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    workspace_id = f"ws-{uuid4().hex[:8]}"
    created = client.post("/v1/jobs", json=_job_payload(workspace_id=workspace_id)).json()
    job_id = created["job_id"]
    _register_arms(client, workspace_id, job_id)

    first = client.post(
        "/v1/assign",
        json={
            "workspace_id": workspace_id,
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
            "workspace_id": workspace_id,
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

    workspace_id = f"ws-{uuid4().hex[:8]}"
    created = client.post("/v1/jobs", json=_job_payload(workspace_id=workspace_id)).json()
    job_id = created["job_id"]
    _register_arms(client, workspace_id, job_id)

    response = client.post(
        "/v1/assign",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "unit_id": "visitor-subset",
            "candidate_arms": ["arm-b"],
            "context": {"country": "CA"},
            "idempotency_key": "req-subset",
        },
    )
    assert response.status_code == 200
    assert response.json()["arm_id"] == "arm-b"


def test_assign_context_schema_rejects_missing_and_disallowed_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    workspace_id = f"ws-{uuid4().hex[:8]}"
    created = client.post(
        "/v1/jobs",
        json=_job_payload(
            workspace_id=workspace_id,
            context_schema_version="v1",
            context_schemas={
                "v1": {
                    "required_fields": ["country"],
                    "allowed_fields": ["country", "device_type", "email"],
                    "redact_fields": ["email"],
                }
            },
        ),
    ).json()
    job_id = created["job_id"]
    _register_arms(client, workspace_id, job_id)

    missing = client.post(
        "/v1/assign",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "unit_id": "visitor-missing",
            "candidate_arms": ["arm-a"],
            "context": {"device_type": "mobile"},
            "idempotency_key": "req-missing-context",
        },
    )
    assert missing.status_code == 400
    assert "missing required" in missing.json()["detail"]

    disallowed = client.post(
        "/v1/assign",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "unit_id": "visitor-disallowed",
            "candidate_arms": ["arm-a"],
            "context": {"country": "US", "unknown_field": True},
            "idempotency_key": "req-disallowed-context",
        },
    )
    assert disallowed.status_code == 400
    assert "disallowed" in disallowed.json()["detail"]


def test_assign_shadow_evaluates_parallel_policy_without_live_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    workspace_id = f"ws-{uuid4().hex[:8]}"
    created = client.post("/v1/jobs", json=_job_payload(workspace_id=workspace_id)).json()
    job_id = created["job_id"]
    _register_arms(client, workspace_id, job_id)

    live_snapshot = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots",
        json={
            "workspace_id": workspace_id,
            "policy_family": "fixed_split",
            "policy_version": "live-v1",
            "payload": {"weights": {"arm-a": 1.0, "arm-b": 0.0}},
        },
    )
    assert live_snapshot.status_code == 200
    live_snapshot_id = live_snapshot.json()["snapshot_id"]
    activate = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots/{live_snapshot_id}/activate",
        json={"workspace_id": workspace_id},
    )
    assert activate.status_code == 200

    snapshot = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots",
        json={
            "workspace_id": workspace_id,
            "policy_family": "fixed_split",
            "policy_version": "shadow-v1",
            "payload": {"weights": {"arm-a": 0.0, "arm-b": 1.0}},
        },
    )
    assert snapshot.status_code == 200
    snapshot_id = snapshot.json()["snapshot_id"]

    live_assign = client.post(
        "/v1/assign",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "unit_id": "visitor-live",
            "candidate_arms": ["arm-a", "arm-b"],
            "context": {"country": "US"},
            "idempotency_key": "req-live",
        },
    )
    assert live_assign.status_code == 200

    shadow_assign = client.post(
        "/v1/assign:shadow",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "unit_id": "visitor-shadow",
            "candidate_arms": ["arm-a", "arm-b"],
            "context": {"country": "US"},
            "idempotency_key": "req-shadow",
            "shadow_snapshot_id": snapshot_id,
        },
    )
    assert shadow_assign.status_code == 200
    body = shadow_assign.json()

    assert body["live_decision"]["arm_id"] == "arm-a"
    assert body["shadow_decision"]["arm_id"] == "arm-b"

    repository = SQLRepository(dependencies.get_session_factory())
    live_persisted = repository.get_decision(live_assign.json()["decision_id"])
    assert live_persisted is not None
    assert repository.get_decision(body["live_decision"]["decision_id"]) is None
    assert repository.get_decision(body["shadow_decision"]["decision_id"]) is None

    events = repository.replay(workspace_id=workspace_id, job_id=job_id)
    assert len([event for event in events if event.event_type == "decision.assigned"]) == 1

    audit = client.get(f"/v1/jobs/{job_id}/audit", params={"workspace_id": workspace_id})
    assert audit.status_code == 200
    actions = [entry["action"] for entry in audit.json()]
    assert "decision.shadow_evaluated" in actions


def test_assign_context_schema_applies_redaction_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    workspace_id = f"ws-{uuid4().hex[:8]}"
    created = client.post(
        "/v1/jobs",
        json=_job_payload(
            workspace_id=workspace_id,
            context_schema_version="v1",
            context_schemas={
                "v1": {
                    "required_fields": ["country"],
                    "allowed_fields": ["country", "email"],
                    "redact_fields": ["email"],
                }
            },
        ),
    ).json()
    job_id = created["job_id"]
    _register_arms(client, workspace_id, job_id)

    response = client.post(
        "/v1/assign",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "unit_id": "visitor-redaction",
            "candidate_arms": ["arm-a"],
            "context": {"country": "US", "email": "person@example.com"},
            "idempotency_key": "req-redaction",
        },
    )
    assert response.status_code == 200
    assert response.json()["context"] == {"country": "US", "email": "[REDACTED]"}

    repository = SQLRepository(dependencies.get_session_factory())
    decision = repository.get_decision(response.json()["decision_id"])
    assert decision is not None
    assert decision.context == {"country": "US", "email": "[REDACTED]"}
