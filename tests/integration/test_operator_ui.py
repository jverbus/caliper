from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api import dependencies
from apps.api.main import create_app as create_api_app
from apps.operator_ui.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


def _job_payload(name: str, workspace_id: str) -> dict[str, object]:
    return {
        "workspace_id": workspace_id,
        "name": name,
        "surface_type": "web",
        "objective_spec": {
            "reward_formula": "1.0 * signup",
            "penalties": ["0.05 * token_cost_usd"],
            "secondary_metrics": ["ctr"],
        },
        "guardrail_spec": {
            "rules": [{"metric": "error_rate", "op": "<", "threshold": 0.01, "action": "pause"}]
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


def test_operator_ui_lists_jobs_and_supports_workspace_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()

    api_client = TestClient(create_api_app())
    first = api_client.post("/v1/jobs", json=_job_payload("A", "ws-a"))
    second = api_client.post("/v1/jobs", json=_job_payload("B", "ws-b"))

    assert first.status_code == 200
    assert second.status_code == 200

    client = TestClient(create_app())

    all_jobs = client.get("/jobs")
    filtered = client.get("/jobs", params={"workspace_id": "ws-a"})

    assert all_jobs.status_code == 200
    assert "Caliper Operator UI" in all_jobs.text
    assert "ws-a" in all_jobs.text
    assert "ws-b" in all_jobs.text

    assert filtered.status_code == 200
    assert "workspace filter: <strong>ws-a</strong>" in filtered.text
    assert "ws-a" in filtered.text
    assert "ws-b" not in filtered.text
