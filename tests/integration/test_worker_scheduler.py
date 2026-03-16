from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from caliper_core.models import (
    Arm,
    ArmType,
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

from apps.api import dependencies
from apps.worker.loop import WorkerLoop
from apps.worker.scheduler_backends import ScheduledTaskDispatch


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


def _epsilon_job() -> Job:
    return Job(
        workspace_id="ws-demo",
        name="Worker epsilon update",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(reward_formula="conversion"),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.EPSILON_GREEDY,
            params={
                "epsilon": 0.1,
                "value_estimates": {"arm-a": 0.4, "arm-b": 0.2},
                "pull_counts": {"arm-a": 5, "arm-b": 5},
                "policy_version": "v3",
            },
            update_cadence=UpdateCadence(mode="periodic", seconds=60),
        ),
        schedule_spec=ScheduleSpec(report_cron=None),
        status=JobStatus.ACTIVE,
    )


def _register_default_arms(repository: SQLRepository, job: Job) -> None:
    repository.upsert_arm(
        Arm(
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            arm_id="arm-a",
            name="Arm A",
            arm_type=ArmType.ARTIFACT,
            payload_ref="web://arm-a",
            metadata={},
        )
    )
    repository.upsert_arm(
        Arm(
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            arm_id="arm-b",
            name="Arm B",
            arm_type=ArmType.ARTIFACT,
            payload_ref="web://arm-b",
            metadata={},
        )
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


def test_worker_policy_update_creates_and_activates_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    monkeypatch.setenv("CALIPER_DB_URL", f"sqlite:///{tmp_path}/scheduler-policy.db")
    _reset_dependency_caches()

    repository = SQLRepository(dependencies.get_session_factory())
    job = repository.create_job(_epsilon_job())
    _register_default_arms(repository, job)

    now = datetime(2026, 3, 14, 10, 44, tzinfo=UTC)
    decisions = [
        repository.create_decision(
            AssignResult(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                unit_id="u-a-1",
                arm_id="arm-a",
                propensity=0.5,
                policy_family=job.policy_spec.policy_family,
                policy_version="v3",
                diagnostics=DecisionDiagnostics(reason="fixture"),
                candidate_arms=["arm-a", "arm-b"],
                context={},
                timestamp=now - timedelta(minutes=4),
            )
        ),
        repository.create_decision(
            AssignResult(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                unit_id="u-a-2",
                arm_id="arm-a",
                propensity=0.5,
                policy_family=job.policy_spec.policy_family,
                policy_version="v3",
                diagnostics=DecisionDiagnostics(reason="fixture"),
                candidate_arms=["arm-a", "arm-b"],
                context={},
                timestamp=now - timedelta(minutes=3),
            )
        ),
        repository.create_decision(
            AssignResult(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                unit_id="u-b-1",
                arm_id="arm-b",
                propensity=0.5,
                policy_family=job.policy_spec.policy_family,
                policy_version="v3",
                diagnostics=DecisionDiagnostics(reason="fixture"),
                candidate_arms=["arm-a", "arm-b"],
                context={},
                timestamp=now - timedelta(minutes=2),
            )
        ),
        repository.create_decision(
            AssignResult(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                unit_id="u-b-2",
                arm_id="arm-b",
                propensity=0.5,
                policy_family=job.policy_spec.policy_family,
                policy_version="v3",
                diagnostics=DecisionDiagnostics(reason="fixture"),
                candidate_arms=["arm-a", "arm-b"],
                context={},
                timestamp=now - timedelta(minutes=1),
            )
        ),
    ]

    for decision in decisions[:2]:
        repository.create_outcome(
            OutcomeCreate(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                decision_id=decision.decision_id,
                unit_id=decision.unit_id,
                events=[
                    OutcomeEvent(
                        outcome_type="conversion",
                        value=1.0,
                        timestamp=decision.timestamp + timedelta(minutes=1),
                    )
                ],
            )
        )
    for decision in decisions[2:]:
        repository.create_outcome(
            OutcomeCreate(
                workspace_id=job.workspace_id,
                job_id=job.job_id,
                decision_id=decision.decision_id,
                unit_id=decision.unit_id,
                events=[
                    OutcomeEvent(
                        outcome_type="conversion",
                        value=0.0,
                        timestamp=decision.timestamp + timedelta(minutes=1),
                    )
                ],
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

    snapshots = repository.list_snapshots(job.workspace_id, job.job_id)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.is_active is True
    assert snapshot.policy_version == "v4"

    pull_counts = snapshot.payload.get("pull_counts")
    value_estimates = snapshot.payload.get("value_estimates")
    assert isinstance(pull_counts, dict)
    assert isinstance(value_estimates, dict)
    assert int(pull_counts["arm-a"]) == 7
    assert int(pull_counts["arm-b"]) == 7
    assert float(value_estimates["arm-a"]) > float(value_estimates["arm-b"])

    policy_events = [
        event
        for event in repository.replay(workspace_id=job.workspace_id, job_id=job.job_id)
        if event.event_type == "policy.updated"
    ]
    assert len(policy_events) == 1
    assert policy_events[0].entity_id == snapshot.snapshot_id

    audit_actions = [
        record.action
        for record in repository.list_audit(workspace_id=job.workspace_id, job_id=job.job_id)
    ]
    assert "policy.snapshot.created" in audit_actions
    assert "policy.snapshot.activated" in audit_actions


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
            events=[
                OutcomeEvent(
                    outcome_type="error_rate",
                    value=0.6,
                    timestamp=decision.timestamp + timedelta(minutes=1),
                )
            ],
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


def test_worker_dispatches_due_tasks_to_scheduler_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    monkeypatch.setenv("CALIPER_DB_URL", f"sqlite:///{tmp_path}/scheduler-5.db")
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
        session.commit()

    dispatched: list[ScheduledTaskDispatch] = []

    class _FakeBackend:
        def dispatch(self, task: ScheduledTaskDispatch) -> dict[str, object]:
            dispatched.append(task)
            return {"backend": "temporal", "workflow_id": "wf-1"}

    loop = WorkerLoop(dependencies.get_session_factory(), scheduler_backend=_FakeBackend())
    result = loop.run_once(now=now, max_due_tasks=10)
    assert result.executed == 1
    assert len(dispatched) == 1

    report = repository.get_latest_report(workspace_id=job.workspace_id, job_id=job.job_id)
    assert report is None

    audit_actions = [
        record.action
        for record in repository.list_audit(workspace_id=job.workspace_id, job_id=job.job_id)
    ]
    assert "worker.task.dispatched" in audit_actions
