from __future__ import annotations

from typing import Any, cast

import pytest
from caliper_storage import SQLRepository
from fastapi.testclient import TestClient

from apps.api import dependencies
from apps.api.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


def _job_payload() -> dict[str, object]:
    return {
        "workspace_id": "ws-demo",
        "name": "Outcome job",
        "surface_type": "web",
        "objective_spec": {
            "reward_formula": "1.0 * signup",
            "penalties": ["0.05 * token_cost_usd", "0.01 * p95_latency_seconds"],
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
            "idempotency_key": f"assign-outcome-{job_id}",
        },
    )
    assert assign.status_code == 200
    return cast(dict[str, Any], assign.json())


def test_outcome_ingest_persists_event_and_is_duplicate_safe(
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
        "events": [
            {"outcome_type": "click", "value": 1, "timestamp": "2026-03-14T16:45:10Z"},
            {"outcome_type": "signup", "value": 1, "timestamp": "2026-03-14T16:47:00Z"},
            {
                "outcome_type": "token_cost_usd",
                "value": 0.03,
                "timestamp": "2026-03-14T16:47:00Z",
            },
            {
                "outcome_type": "p95_latency_seconds",
                "value": 1.2,
                "timestamp": "2026-03-14T16:47:00Z",
            },
        ],
        "attribution_window": {"hours": 48},
        "metadata": {"source": "webhook"},
    }

    first = client.post("/v1/outcomes", json=payload)
    assert first.status_code == 200

    duplicate = client.post("/v1/outcomes", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()

    repository = SQLRepository(dependencies.get_session_factory())
    outcomes = repository.list_outcomes(workspace_id="ws-demo", job_id=job_id)
    assert len(outcomes) == 1
    assert outcomes[0].decision_id == decision["decision_id"]
    assert outcomes[0].attribution_window.hours == 48

    events = repository.replay(workspace_id="ws-demo", job_id=job_id)
    observed = [event for event in events if event.event_type == "outcome.observed"]
    assert len(observed) == 1
    assert observed[0].entity_id == decision["decision_id"]
    assert observed[0].payload["arm_id"] == decision["arm_id"]


def test_outcome_requires_matching_decision_context(
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
        "/v1/outcomes",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "decision_id": decision["decision_id"],
            "unit_id": "visitor-2",
            "events": [
                {
                    "outcome_type": "signup",
                    "value": 1,
                    "timestamp": "2026-03-14T16:47:00Z",
                }
            ],
            "attribution_window": {"hours": 24},
            "metadata": {},
        },
    )
    assert mismatched.status_code == 400


def test_outcome_rejects_unknown_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]

    missing = client.post(
        "/v1/outcomes",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "decision_id": "dec_missing",
            "unit_id": "visitor-1",
            "events": [
                {
                    "outcome_type": "signup",
                    "value": 1,
                    "timestamp": "2026-03-14T16:47:00Z",
                }
            ],
            "attribution_window": {"hours": 24},
            "metadata": {},
        },
    )
    assert missing.status_code == 404
