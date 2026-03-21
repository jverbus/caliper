from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api import dependencies
from apps.api.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.reset_dependency_caches()


def _job_payload(workspace_id: str) -> dict[str, object]:
    return {
        "workspace_id": workspace_id,
        "name": "Schema characterization job",
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


def _register_arm(client: TestClient, workspace_id: str, job_id: str) -> None:
    response = client.post(
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
                }
            ],
        },
    )
    assert response.status_code == 200


def _create_decision(client: TestClient, workspace_id: str, job_id: str) -> dict[str, Any]:
    assign = client.post(
        "/v1/assign",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "unit_id": "visitor-1",
            "candidate_arms": ["arm-a"],
            "context": {"country": "US"},
            "idempotency_key": f"assign-schema-{job_id}",
        },
    )
    assert assign.status_code == 200
    return cast(dict[str, Any], assign.json())


def test_high_traffic_endpoint_response_shapes_are_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    workspace_id = f"ws-{uuid4().hex[:8]}"
    created = client.post("/v1/jobs", json=_job_payload(workspace_id)).json()
    job_id = created["job_id"]
    _register_arm(client, workspace_id, job_id)

    assign_body = _create_decision(client, workspace_id, job_id)
    assert set(assign_body.keys()) == {
        "decision_id",
        "workspace_id",
        "job_id",
        "unit_id",
        "arm_id",
        "candidate_arms",
        "propensity",
        "policy_family",
        "policy_version",
        "context_schema_version",
        "context",
        "diagnostics",
        "timestamp",
    }

    exposure = client.post(
        "/v1/exposures",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "decision_id": assign_body["decision_id"],
            "unit_id": "visitor-1",
            "exposure_type": "rendered",
            "timestamp": "2026-03-14T16:45:00Z",
            "metadata": {"page": "/pricing", "http_status": 200},
        },
    )
    assert exposure.status_code == 200
    exposure_body = cast(dict[str, Any], exposure.json())
    assert set(exposure_body.keys()) == {
        "workspace_id",
        "job_id",
        "decision_id",
        "unit_id",
        "exposure_type",
        "timestamp",
        "metadata",
    }

    outcome = client.post(
        "/v1/outcomes",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "decision_id": assign_body["decision_id"],
            "unit_id": "visitor-1",
            "events": [
                {"outcome_type": "signup", "value": 1, "timestamp": "2026-03-14T16:47:00Z"}
            ],
            "attribution_window": {"hours": 24},
            "metadata": {"source": "webhook"},
        },
    )
    assert outcome.status_code == 200
    outcome_body = cast(dict[str, Any], outcome.json())
    assert set(outcome_body.keys()) == {
        "workspace_id",
        "job_id",
        "decision_id",
        "unit_id",
        "events",
        "attribution_window",
        "metadata",
    }
