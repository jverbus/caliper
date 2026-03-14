from __future__ import annotations

import pytest
from api import dependencies
from api.main import create_app
from fastapi.testclient import TestClient


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


def _job_payload() -> dict[str, object]:
    return {
        "workspace_id": "ws-demo",
        "name": "Snapshot job",
        "surface_type": "web",
        "objective_spec": {
            "reward_formula": "1.0 * signup",
            "penalties": [],
            "secondary_metrics": [],
        },
        "guardrail_spec": {"rules": []},
        "policy_spec": {
            "policy_family": "fixed_split",
            "params": {"weights": {"arm-a": 0.8, "arm-b": 0.2}},
            "update_cadence": {"mode": "periodic", "seconds": 300},
            "context_schema_version": None,
        },
        "segment_spec": {"dimensions": []},
        "schedule_spec": {"report_cron": "0 7 * * *"},
    }


def _register_arms(client: TestClient, job_id: str) -> None:
    response = client.post(
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
    assert response.status_code == 200


def test_policy_snapshot_activation_and_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]
    _register_arms(client, job_id)

    v1 = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots",
        json={
            "workspace_id": "ws-demo",
            "policy_family": "fixed_split",
            "policy_version": "v1",
            "payload": {"weights": {"arm-a": 0.9, "arm-b": 0.1}},
        },
    )
    assert v1.status_code == 200
    v1_snapshot = v1.json()

    v2 = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots",
        json={
            "workspace_id": "ws-demo",
            "policy_family": "fixed_split",
            "policy_version": "v2",
            "payload": {"weights": {"arm-a": 0.1, "arm-b": 0.9}},
        },
    )
    assert v2.status_code == 200
    v2_snapshot = v2.json()

    promote_v2 = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots/{v2_snapshot['snapshot_id']}/promote",
        json={"workspace_id": "ws-demo"},
    )
    assert promote_v2.status_code == 200

    assign_v2 = client.post(
        "/v1/assign",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "unit_id": "visitor-v2",
            "candidate_arms": ["arm-a", "arm-b"],
            "context": {},
            "idempotency_key": f"assign-v2-{job_id}",
        },
    )
    assert assign_v2.status_code == 200
    assert assign_v2.json()["policy_version"] == "v2"
    assert assign_v2.json()["diagnostics"]["scores"] == {"arm-a": 0.1, "arm-b": 0.9}

    rollback = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots/rollback",
        json={"workspace_id": "ws-demo", "target_snapshot_id": v1_snapshot["snapshot_id"]},
    )
    assert rollback.status_code == 200
    assert rollback.json()["policy_version"] == "v1"

    assign_v1 = client.post(
        "/v1/assign",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "unit_id": "visitor-v1",
            "candidate_arms": ["arm-a", "arm-b"],
            "context": {},
            "idempotency_key": f"assign-v1-{job_id}",
        },
    )
    assert assign_v1.status_code == 200
    assert assign_v1.json()["policy_version"] == "v1"
    assert assign_v1.json()["diagnostics"]["scores"] == {"arm-a": 0.9, "arm-b": 0.1}

    resume_to_active = client.post(
        f"/v1/jobs/{job_id}/resume",
        json={"workspace_id": "ws-demo", "approval_state": "approved"},
    )
    assert resume_to_active.status_code == 200

    pause = client.post(
        f"/v1/jobs/{job_id}/pause",
        json={"workspace_id": "ws-demo", "approval_state": "pending"},
    )
    assert pause.status_code == 200

    resume = client.post(
        f"/v1/jobs/{job_id}/resume",
        json={"workspace_id": "ws-demo", "approval_state": "approved"},
    )
    assert resume.status_code == 200

    audit = client.get(f"/v1/jobs/{job_id}/audit", params={"workspace_id": "ws-demo"})
    assert audit.status_code == 200
    actions = [entry["action"] for entry in audit.json()]
    assert "job.pause" in actions
    assert "job.resume" in actions
    assert "policy.snapshot.activated" in actions
    assert "policy.snapshot.rollback" in actions


def test_contextual_promotion_gate_blocks_activation_without_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]
    _register_arms(client, job_id)

    contextual_snapshot = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots",
        json={
            "workspace_id": "ws-demo",
            "policy_family": "fixed_split",
            "policy_version": "ctx-v1",
            "payload": {
                "weights": {"arm-a": 0.5, "arm-b": 0.5},
                "runtime": "contextual",
                "contextual_gate": {
                    "shadow_mode_validated": False,
                    "ope_backtest_validated": False,
                    "manual_review_approved": False,
                    "context_schema_version": None,
                },
            },
        },
    )
    assert contextual_snapshot.status_code == 200
    snapshot_id = contextual_snapshot.json()["snapshot_id"]

    gate = client.get(
        f"/v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/contextual-gate",
        params={"workspace_id": "ws-demo"},
    )
    assert gate.status_code == 200
    gate_body = gate.json()
    assert gate_body["is_contextual_runtime"] is True
    assert gate_body["passed"] is False
    assert "contextual_gate.shadow_mode_validated must be true" in gate_body["failures"]
    assert "contextual_gate.ope_backtest_validated must be true" in gate_body["failures"]
    assert "contextual_gate.manual_review_approved must be true" in gate_body["failures"]
    assert "contextual_gate.context_schema_version is required" in gate_body["failures"]
    assert (
        "at least one shadow evaluation is required before contextual activation"
        in gate_body["failures"]
    )

    activate = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/activate",
        json={"workspace_id": "ws-demo"},
    )
    assert activate.status_code == 409
    assert activate.json()["detail"]["message"] == "Contextual promotion gate checks failed."


def test_contextual_promotion_gate_allows_activation_after_non_live_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    payload = _job_payload()
    created = client.post("/v1/jobs", json=payload).json()
    job_id = created["job_id"]
    _register_arms(client, job_id)

    live_snapshot = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots",
        json={
            "workspace_id": "ws-demo",
            "policy_family": "fixed_split",
            "policy_version": "live-v1",
            "payload": {"weights": {"arm-a": 0.9, "arm-b": 0.1}},
        },
    )
    assert live_snapshot.status_code == 200
    live_snapshot_id = live_snapshot.json()["snapshot_id"]

    activate_live = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots/{live_snapshot_id}/activate",
        json={"workspace_id": "ws-demo"},
    )
    assert activate_live.status_code == 200

    contextual_snapshot = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots",
        json={
            "workspace_id": "ws-demo",
            "policy_family": "fixed_split",
            "policy_version": "ctx-v1",
            "payload": {
                "weights": {"arm-a": 0.2, "arm-b": 0.8},
                "runtime": "contextual",
                "requires_contextual_gate": True,
                "contextual_gate": {
                    "shadow_mode_validated": True,
                    "ope_backtest_validated": True,
                    "manual_review_approved": True,
                    "context_schema_version": "workflow.v1",
                },
            },
        },
    )
    assert contextual_snapshot.status_code == 200
    snapshot_id = contextual_snapshot.json()["snapshot_id"]

    shadow_eval = client.post(
        "/v1/assign:shadow",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "unit_id": "user-ctx",
            "candidate_arms": ["arm-a", "arm-b"],
            "context": {},
            "idempotency_key": "ctx-shadow-eval",
            "shadow_snapshot_id": snapshot_id,
        },
    )
    assert shadow_eval.status_code == 200

    gate = client.get(
        f"/v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/contextual-gate",
        params={"workspace_id": "ws-demo"},
    )
    assert gate.status_code == 200
    assert gate.json()["passed"] is True

    activate = client.post(
        f"/v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/activate",
        json={"workspace_id": "ws-demo"},
    )
    assert activate.status_code == 200
    assert activate.json()["policy_version"] == "ctx-v1"
