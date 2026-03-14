from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from api import dependencies
from caliper_core.models import (
    AssignResult,
    DecisionDiagnostics,
    GuardrailAction,
    GuardrailRule,
    GuardrailSpec,
    Job,
    JobStatus,
    ObjectiveSpec,
    OutcomeCreate,
    OutcomeEvent,
    PolicyFamily,
    PolicySpec,
    ScheduleSpec,
    SurfaceType,
    UpdateCadence,
)
from caliper_storage import SQLRepository
from caliper_storage.sqlalchemy_models import ScheduledTaskRow
from worker.loop import WorkerLoop


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


def _active_job() -> Job:
    return Job(
        workspace_id="ws-demo",
        name="Worker test job",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(
            reward_formula="signup - token_cost_usd",
            penalties=["0.1 * p95_latency_seconds"],
            secondary_metrics=["ctr"],
        ),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.FIXED_SPLIT,
            params={"weights": {"arm-a": 1.0}},
            update_cadence=UpdateCadence(mode="periodic", seconds=60),
        ),
        schedule_spec=ScheduleSpec(report_cron="0 7 * * *"),
        status=JobStatus.ACTIVE,
    )


def test_worker_schedules_periodic_report_and_policy_tasks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    monkeypatch.setenv("CALIPER_DB_URL", f"sqlite:///{tmp_path}/scheduler-1.db")
    _reset_dependency_caches()

    repository = SQLRepository(dependencies.get_session_factory())
    job = repository.create_job(_active_job())

    loop = WorkerLoop(dependencies.get_session_factory())
    result = loop.run_once(now=datetime(2026, 3, 14, 10, 44, tzinfo=UTC), max_due_tasks=10)
    assert result.scheduled == 2

    with dependencies.get_session_factory()() as session:
        rows = session.query(ScheduledTaskRow).filter(ScheduledTaskRow.job_id == job.job_id).all()

    task_types = sorted(row.task_type for row in rows)
    assert task_types == ["generate_report", "run_policy_update"]


def test_worker_executes_due_tasks_and_persists_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    monkeypatch.setenv("CALIPER_DB_URL", f"sqlite:///{tmp_path}/scheduler-2.db")
    _reset_dependency_caches()

    repository = SQLRepository(dependencies.get_session_factory())
    job = repository.create_job(_active_job())

    now = datetime(2026, 3, 14, 10, 44, tzinfo=UTC)
    with dependencies.get_session_factory()() as session:
        session.add(
            ScheduledTaskRow(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                task_type="generate_report",
                due_at=now - timedelta(minutes=1),
                status="pending",
                payload_json={},
                created_at=now,
                updated_at=now,
                started_at=None,
                completed_at=None,
                attempt_count=0,
                last_error=None,
            )
        )
        session.add(
            ScheduledTaskRow(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                task_type="run_policy_update",
                due_at=now - timedelta(minutes=1),
                status="pending",
                payload_json={},
                created_at=now,
                updated_at=now,
                started_at=None,
                completed_at=None,
                attempt_count=0,
                last_error=None,
            )
        )
        session.commit()

    loop = WorkerLoop(dependencies.get_session_factory())
    result = loop.run_once(now=now, max_due_tasks=10)
    assert result.executed == 2

    report = repository.get_latest_report(workspace_id=job.workspace_id, job_id=job.job_id)
    assert report is not None

    audit_actions = [
        record.action
        for record in repository.list_audit(workspace_id=job.workspace_id, job_id=job.job_id)
    ]
    assert "worker.report.generated" in audit_actions
    assert "worker.policy.updated" in audit_actions


def test_due_task_survives_worker_restart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    monkeypatch.setenv("CALIPER_DB_URL", f"sqlite:///{tmp_path}/scheduler-3.db")
    _reset_dependency_caches()

    repository = SQLRepository(dependencies.get_session_factory())
    job = repository.create_job(_active_job())

    due_at = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
    with dependencies.get_session_factory()() as session:
        session.add(
            ScheduledTaskRow(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                task_type="generate_report",
                due_at=due_at,
                status="pending",
                payload_json={},
                created_at=due_at,
                updated_at=due_at,
                started_at=None,
                completed_at=None,
                attempt_count=0,
                last_error=None,
            )
        )
        session.commit()

    restarted_loop = WorkerLoop(dependencies.get_session_factory())
    restarted_loop.run_once(now=datetime(2026, 3, 14, 10, 44, tzinfo=UTC), max_due_tasks=10)

    report = repository.get_latest_report(workspace_id=job.workspace_id, job_id=job.job_id)
    assert report is not None


def test_worker_guardrail_breach_pauses_job_and_records_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    monkeypatch.setenv("CALIPER_DB_URL", f"sqlite:///{tmp_path}/scheduler-4.db")
    _reset_dependency_caches()

    repository = SQLRepository(dependencies.get_session_factory())
    job = _active_job().model_copy(
        update={
            "guardrail_spec": GuardrailSpec(
                rules=[
                    GuardrailRule(
                        metric="error_rate",
                        op=">",
                        threshold=0.2,
                        action=GuardrailAction.PAUSE,
                    )
                ]
            )
        }
    )
    job = repository.create_job(job)
    now = datetime(2026, 3, 14, 10, 44, tzinfo=UTC)

    decision = repository.create_decision(
        AssignResult(
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            unit_id="u-1",
            arm_id="arm-a",
            propensity=1.0,
            policy_family=job.policy_spec.policy_family,
            policy_version="v1",
            diagnostics=DecisionDiagnostics(reason="fixture"),
            candidate_arms=["arm-a"],
            context={},
            timestamp=now,
        )
    )
    repository.create_outcome(
        OutcomeCreate(
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            decision_id=decision.decision_id,
            unit_id=decision.unit_id,
            events=[OutcomeEvent(outcome_type="error_rate", value=0.6)],
        )
    )

    with dependencies.get_session_factory()() as session:
        session.add(
            ScheduledTaskRow(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                task_type="run_policy_update",
                due_at=now - timedelta(minutes=1),
                status="pending",
                payload_json={},
                created_at=now,
                updated_at=now,
                started_at=None,
                completed_at=None,
                attempt_count=0,
                last_error=None,
            )
        )
        session.commit()

    loop = WorkerLoop(dependencies.get_session_factory())
    result = loop.run_once(now=now, max_due_tasks=10)
    assert result.executed == 1

    updated_job = repository.get_job(job.job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.PAUSED

    guardrail_events = repository.list_guardrail_events(job.workspace_id, job.job_id)
    assert len(guardrail_events) == 1
    assert guardrail_events[0]["action"] == GuardrailAction.PAUSE.value
