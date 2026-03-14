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
        "name": "Report job",
        "surface_type": "web",
        "objective_spec": {
            "reward_formula": "signup - token_cost_usd",
            "penalties": ["0.1 * p95_latency_seconds"],
            "secondary_metrics": ["ctr"],
        },
        "guardrail_spec": {"rules": []},
        "policy_spec": {
            "policy_family": "fixed_split",
            "params": {"weights": {"arm-a": 1.0, "arm-b": 1.0}},
            "update_cadence": {"mode": "periodic", "seconds": 300},
            "context_schema_version": None,
        },
        "segment_spec": {"dimensions": ["country"]},
        "schedule_spec": {"report_cron": "0 7 * * *"},
    }


def test_report_generation_and_latest_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    created = client.post("/v1/jobs", json=_job_payload()).json()
    job_id = created["job_id"]

    client.post(
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

    assign = client.post(
        "/v1/assign",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "unit_id": "visitor-1",
            "candidate_arms": ["arm-a"],
            "context": {"country": "US"},
            "idempotency_key": f"assign-report-{job_id}",
        },
    )
    decision_id = assign.json()["decision_id"]

    client.post(
        "/v1/outcomes",
        json={
            "workspace_id": "ws-demo",
            "job_id": job_id,
            "decision_id": decision_id,
            "unit_id": "visitor-1",
            "events": [
                {"outcome_type": "signup", "value": 1, "timestamp": "2026-03-14T16:47:00Z"},
                {
                    "outcome_type": "token_cost_usd",
                    "value": 0.1,
                    "timestamp": "2026-03-14T16:47:00Z",
                },
            ],
            "attribution_window": {"hours": 24},
            "metadata": {},
        },
    )

    generated = client.post(
        f"/v1/jobs/{job_id}/reports:generate",
        json={"workspace_id": "ws-demo"},
    )
    assert generated.status_code == 200
    report = generated.json()
    assert report["job_id"] == job_id
    assert isinstance(report["leaders"], list)
    assert "## Leaders" in report["markdown"]
    assert report["html"].startswith("<html>")

    latest = client.get(f"/v1/jobs/{job_id}/reports/latest", params={"workspace_id": "ws-demo"})
    assert latest.status_code == 200
    assert latest.json()["report_id"] == report["report_id"]
