from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api import dependencies
from apps.api.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


def test_autotune_lifecycle_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    experiment_id = f"exp-{uuid4().hex[:8]}"
    baseline = client.post(
        "/v1/autotune/candidates",
        json={
            "experiment_id": experiment_id,
            "candidate_type": "prompt",
            "editable_surface": "mcp_prompt_text",
            "content": {"prompt": "baseline"},
            "complexity_score": 0.1,
        },
    )
    assert baseline.status_code == 200
    baseline_id = baseline.json()["candidate_id"]

    candidate = client.post(
        "/v1/autotune/candidates",
        json={
            "experiment_id": experiment_id,
            "candidate_type": "prompt",
            "parent_candidate_id": baseline_id,
            "editable_surface": "mcp_prompt_text",
            "content": {"prompt": "candidate"},
            "complexity_score": 0.2,
        },
    )
    assert candidate.status_code == 200
    candidate_id = candidate.json()["candidate_id"]

    listed = client.get("/v1/autotune/candidates", params={"experiment_id": experiment_id})
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    run = client.post(
        "/v1/autotune/runs",
        json={
            "experiment_id": experiment_id,
            "candidate_id": candidate_id,
            "baseline_candidate_id": baseline_id,
            "seed": 42,
            "budget": 1500,
            "simulation_config_snapshot": {"runtime_window_minutes": 45},
            "evaluator_version": "fixed-v1",
        },
    )
    assert run.status_code == 200
    run_id = run.json()["run_id"]

    status = client.get(f"/v1/autotune/runs/{run_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"

    result = client.get(f"/v1/autotune/runs/{run_id}/result")
    assert result.status_code == 200
    assert result.json()["run_id"] == run_id
    score_breakdown = result.json()["score_breakdown"]
    assert "candidate_score" in score_breakdown
    assert "baseline_score" in score_breakdown
    assert "delta_vs_baseline" in score_breakdown

    assert result.json()["keep_discard"] in {"keep", "discard"}
    assert isinstance(result.json()["reason"], str)

    kept = client.post(
        f"/v1/autotune/runs/{run_id}/keep",
        params={"reason": "human override: keep"},
    )
    assert kept.status_code == 200
    assert kept.json()["keep_discard"] == "keep"

    promoted = client.post(
        "/v1/autotune/promote",
        json={
            "candidate_id": candidate_id,
            "run_id": run_id,
            "promoted_by": "human-operator",
            "target_surface": "caliper://agent_playbook",
            "confirmation": "CONFIRM_AUTOTUNE_PROMOTION",
        },
    )
    assert promoted.status_code == 200
    diff_payload = promoted.json()["diff_summary"]
    assert '"summary": "what_changed:' in diff_payload
    assert '"run_id":' in diff_payload
    assert promoted.json()["promoted_content"] == {"prompt": "candidate"}
    assert promoted.json()["replay_check"]["passed"] is True

    exported = client.get("/v1/autotune/export.jsonl", params={"experiment_id": experiment_id})
    assert exported.status_code == 200
    assert run_id in exported.json()["jsonl"]


def test_autotune_run_auto_disposition_covers_keep_and_discard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    experiment_id = f"exp-{uuid4().hex[:8]}"
    baseline = client.post(
        "/v1/autotune/candidates",
        json={
            "experiment_id": experiment_id,
            "candidate_type": "prompt",
            "editable_surface": "mcp_prompt_text",
            "content": {"prompt": "baseline copy"},
            "complexity_score": 0.0,
        },
    )
    assert baseline.status_code == 200
    baseline_id = baseline.json()["candidate_id"]

    candidate = client.post(
        "/v1/autotune/candidates",
        json={
            "experiment_id": experiment_id,
            "candidate_type": "prompt",
            "parent_candidate_id": baseline_id,
            "editable_surface": "mcp_prompt_text",
            "content": {
                "prompt": "candidate copy with modest changes",
                "tone": "friendly",
            },
            "complexity_score": 0.0,
        },
    )
    assert candidate.status_code == 200
    candidate_id = candidate.json()["candidate_id"]

    seen_keep = False
    seen_discard = False
    for seed in range(1, 250):
        run = client.post(
            "/v1/autotune/runs",
            json={
                "experiment_id": experiment_id,
                "candidate_id": candidate_id,
                "baseline_candidate_id": baseline_id,
                "seed": seed,
                "budget": 1500,
                "simulation_config_snapshot": {"runtime_window_minutes": 45},
                "evaluator_version": "fixed-v1",
            },
        )
        assert run.status_code == 200
        run_id = run.json()["run_id"]

        result = client.get(f"/v1/autotune/runs/{run_id}/result")
        assert result.status_code == 200
        payload = result.json()
        assert payload["reason"]
        seen_keep = seen_keep or payload["keep_discard"] == "keep"
        seen_discard = seen_discard or payload["keep_discard"] == "discard"
        if seen_keep and seen_discard:
            break

    assert seen_keep is True
    assert seen_discard is True


def test_autotune_promotion_requires_confirmation_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    experiment_id = f"exp-{uuid4().hex[:8]}"
    baseline = client.post(
        "/v1/autotune/candidates",
        json={
            "experiment_id": experiment_id,
            "candidate_type": "prompt",
            "editable_surface": "mcp_prompt_text",
            "content": {"prompt": "baseline"},
            "complexity_score": 0.0,
        },
    )
    baseline_id = baseline.json()["candidate_id"]

    candidate = client.post(
        "/v1/autotune/candidates",
        json={
            "experiment_id": experiment_id,
            "candidate_type": "prompt",
            "parent_candidate_id": baseline_id,
            "editable_surface": "mcp_prompt_text",
            "content": {"prompt": "candidate"},
            "complexity_score": 0.0,
        },
    )
    candidate_id = candidate.json()["candidate_id"]

    run = client.post(
        "/v1/autotune/runs",
        json={
            "experiment_id": experiment_id,
            "candidate_id": candidate_id,
            "baseline_candidate_id": baseline_id,
            "seed": 99,
            "budget": 800,
            "simulation_config_snapshot": {"runtime_window_minutes": 30},
            "evaluator_version": "fixed-v1",
        },
    )
    run_id = run.json()["run_id"]

    promoted = client.post(
        "/v1/autotune/promote",
        json={
            "candidate_id": candidate_id,
            "run_id": run_id,
            "promoted_by": "human-operator",
            "target_surface": "caliper://agent_playbook",
            "confirmation": "CONFIRM_PROMOTION",
        },
    )
    assert promoted.status_code == 400
    assert "confirmation token mismatch" in promoted.json()["detail"]


def test_autotune_candidate_rejects_forbidden_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    response = client.post(
        "/v1/autotune/candidates",
        json={
            "experiment_id": f"exp-{uuid4().hex[:8]}",
            "candidate_type": "prompt",
            "editable_surface": "decision_service.py",
            "content": {"prompt": "not allowed"},
            "complexity_score": 0.1,
        },
    )
    assert response.status_code == 400
    assert "not allowed in v1" in response.json()["detail"]
