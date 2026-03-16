from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from caliper_core.events import EventEnvelope
from caliper_core.models import (
    ApprovalState,
    ArmState,
    GuardrailAction,
    Job,
    JobStatus,
    PolicySnapshot,
)
from caliper_policies.updater import PolicyUpdater
from caliper_reports import ReportGenerator
from caliper_reward import GuardrailEngine
from caliper_reward.engine import RewardEngine
from caliper_storage import SQLRepository
from caliper_storage.sqlalchemy_models import JobRow, ScheduledTaskRow
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from apps.worker.scheduler_backends import ScheduledTaskDispatch, SchedulerBackend


@dataclass(frozen=True)
class WorkerRunResult:
    scheduled: int = 0
    executed: int = 0


class WorkerLoop:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        scheduler_backend: SchedulerBackend | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._scheduler_backend = scheduler_backend
        self._repository = SQLRepository(session_factory)
        self._report_generator = ReportGenerator()
        self._reward_engine = RewardEngine()
        self._guardrail_engine = GuardrailEngine()
        self._policy_updater = PolicyUpdater()

    def run_once(self, *, now: datetime | None = None, max_due_tasks: int = 25) -> WorkerRunResult:
        run_at = _as_aware_utc(now)
        scheduled = self._schedule_periodic_tasks(run_at)
        executed = self._run_due_tasks(run_at, limit=max_due_tasks)
        return WorkerRunResult(scheduled=scheduled, executed=executed)

    def _schedule_periodic_tasks(self, now: datetime) -> int:
        jobs = self._list_active_jobs()
        created = 0

        for job in jobs:
            report_due = _next_report_due(job=job, now=now)
            if report_due is not None and self._enqueue_if_missing(
                job=job,
                task_type="generate_report",
                due_at=report_due,
            ):
                created += 1

            policy_due = _next_policy_due(job=job, now=now)
            if policy_due is not None and self._enqueue_if_missing(
                job=job,
                task_type="run_policy_update",
                due_at=policy_due,
            ):
                created += 1

        return created

    def _run_due_tasks(self, now: datetime, *, limit: int) -> int:
        with self._session_factory() as session:
            due = session.scalars(
                select(ScheduledTaskRow)
                .where(
                    ScheduledTaskRow.status == "pending",
                    ScheduledTaskRow.due_at <= now,
                )
                .order_by(ScheduledTaskRow.due_at.asc(), ScheduledTaskRow.task_id.asc())
                .limit(limit)
            ).all()

            for row in due:
                row.status = "running"
                row.started_at = now
                row.updated_at = now
            session.commit()

        for task in due:
            self._execute_task(task=task, now=now)

        return len(due)

    def _execute_task(self, *, task: ScheduledTaskRow, now: datetime) -> None:
        error_text: str | None = None
        dispatch_metadata: dict[str, object] | None = None
        try:
            if self._scheduler_backend is not None:
                dispatch_metadata = self._scheduler_backend.dispatch(
                    ScheduledTaskDispatch(
                        task_id=task.task_id,
                        workspace_id=task.workspace_id,
                        job_id=task.job_id,
                        task_type=task.task_type,
                    )
                )
                self._repository.append_audit(
                    task.workspace_id,
                    task.job_id,
                    "worker.task.dispatched",
                    {
                        "task_id": task.task_id,
                        "task_type": task.task_type,
                        **dispatch_metadata,
                    },
                )
            elif task.task_type == "generate_report":
                self._execute_report(task.workspace_id, task.job_id)
            elif task.task_type == "run_policy_update":
                self._execute_policy_update(task.workspace_id, task.job_id)
            else:
                raise ValueError(f"Unsupported task type: {task.task_type}")
        except Exception as exc:  # pragma: no cover - exercised in integration with bad fixtures
            error_text = str(exc)

        with self._session_factory() as session:
            row = session.get(ScheduledTaskRow, task.task_id)
            if row is None:
                return

            if error_text is None:
                row.status = "completed"
                row.completed_at = now
                row.last_error = None
                row.attempt_count += 1
            else:
                row.status = "pending"
                row.due_at = now + timedelta(minutes=1)
                row.last_error = error_text[:1000]
                row.attempt_count += 1
            row.updated_at = now
            session.add(row)
            session.commit()

    def _execute_report(self, workspace_id: str, job_id: str) -> None:
        job = self._repository.get_job(job_id)
        if job is None or job.workspace_id != workspace_id:
            return

        arms = self._repository.list_arms(workspace_id, job_id)
        decisions = self._repository.list_decisions(workspace_id, job_id)
        exposures = self._repository.list_exposures(workspace_id, job_id)
        outcomes = self._repository.list_outcomes(workspace_id, job_id)
        guardrails = self._repository.list_guardrail_events(workspace_id, job_id)
        report = self._report_generator.generate(
            job=job,
            arms=arms,
            decisions=decisions,
            exposures=exposures,
            outcomes=outcomes,
            guardrails=guardrails,
        )
        self._repository.save_report(report)
        self._repository.append_audit(
            workspace_id,
            job_id,
            "worker.report.generated",
            {"report_id": report.report_id},
        )

    def _execute_policy_update(self, workspace_id: str, job_id: str) -> None:
        job = self._repository.get_job(job_id)
        if job is None or job.workspace_id != workspace_id:
            return

        active_snapshot = self._repository.get_active_snapshot(workspace_id, job_id)
        effective_job = self._effective_policy_job(job=job, active_snapshot=active_snapshot)

        decisions = self._repository.list_decisions(workspace_id, job_id)
        outcomes = self._repository.list_outcomes(workspace_id, job_id)
        dataset = self._reward_engine.build_policy_update_dataset(
            objective_spec=effective_job.objective_spec,
            decisions=decisions,
            outcomes=outcomes,
        )
        self._repository.append_audit(
            workspace_id,
            job_id,
            "worker.policy.updated",
            {"record_count": len(dataset)},
        )

        evaluations = self._guardrail_engine.evaluate(
            workspace_id=workspace_id,
            job_id=job_id,
            guardrail_spec=effective_job.guardrail_spec,
            records=dataset,
        )

        for evaluation in evaluations:
            self._repository.create_guardrail_event(evaluation.event)
            self._apply_guardrail_action(
                workspace_id=workspace_id,
                job_id=job_id,
                action=evaluation.event.action,
                target_arm_id=evaluation.target_arm_id,
            )
            self._repository.append_audit(
                workspace_id,
                job_id,
                "worker.guardrail.action",
                {
                    "guardrail_event_id": evaluation.event.guardrail_event_id,
                    "metric": evaluation.event.metric,
                    "action": evaluation.event.action.value if evaluation.event.action else None,
                    "target_arm_id": evaluation.target_arm_id,
                    "observed": evaluation.event.metadata.get("observed"),
                },
            )

        arms = self._repository.list_arms(workspace_id, job_id)
        update = self._policy_updater.update(job=effective_job, arms=arms, records=dataset)
        if update is None:
            self._repository.append_audit(
                workspace_id,
                job_id,
                "worker.policy.noop",
                {
                    "policy_family": effective_job.policy_spec.policy_family.value,
                    "record_count": len(dataset),
                    "reason": "unsupported_policy_family_or_no_records",
                },
            )
            return

        policy_version = self._next_policy_version(
            active_snapshot=active_snapshot,
            effective_job=effective_job,
        )
        snapshot = self._repository.save_snapshot(
            PolicySnapshot(
                workspace_id=workspace_id,
                job_id=job_id,
                policy_family=effective_job.policy_spec.policy_family,
                policy_version=policy_version,
                payload=update.params,
                is_active=False,
            )
        )
        self._repository.append_audit(
            workspace_id,
            job_id,
            "policy.snapshot.created",
            {
                "snapshot_id": snapshot.snapshot_id,
                "policy_version": snapshot.policy_version,
                "record_count": update.record_count,
                "updated_arm_ids": list(update.updated_arm_ids),
                "auto_generated": True,
            },
        )
        self._repository.append(
            EventEnvelope(
                workspace_id=workspace_id,
                job_id=job_id,
                event_type="policy.snapshot.created",
                entity_id=snapshot.snapshot_id,
                payload={
                    "snapshot_id": snapshot.snapshot_id,
                    "policy_family": snapshot.policy_family.value,
                    "policy_version": snapshot.policy_version,
                    "record_count": update.record_count,
                    "updated_arm_ids": list(update.updated_arm_ids),
                    "auto_generated": True,
                },
            )
        )

        blocking_actions = {GuardrailAction.PAUSE, GuardrailAction.REQUIRE_MANUAL_RESUME}
        guardrail_blocked = any(
            evaluation.event.action in blocking_actions for evaluation in evaluations
        )
        current_job = self._repository.get_job(job_id)
        status_blocked = current_job is None or current_job.status != JobStatus.ACTIVE
        if guardrail_blocked or status_blocked:
            self._repository.append_audit(
                workspace_id,
                job_id,
                "policy.snapshot.pending",
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "policy_version": snapshot.policy_version,
                    "reason": (
                        "guardrail_blocked" if guardrail_blocked else "job_not_active_after_update"
                    ),
                },
            )
            return

        activated = self._repository.activate_snapshot(
            workspace_id=workspace_id,
            job_id=job_id,
            snapshot_id=snapshot.snapshot_id,
        )
        if activated is None:
            return

        self._repository.append(
            EventEnvelope(
                workspace_id=workspace_id,
                job_id=job_id,
                event_type="policy.updated",
                entity_id=activated.snapshot_id,
                payload={
                    "snapshot_id": activated.snapshot_id,
                    "policy_family": activated.policy_family.value,
                    "policy_version": activated.policy_version,
                    "activated_at": (
                        activated.activated_at.isoformat() if activated.activated_at else None
                    ),
                    "auto_generated": True,
                },
            )
        )
        self._repository.append_audit(
            workspace_id,
            job_id,
            "policy.snapshot.activated",
            {
                "snapshot_id": activated.snapshot_id,
                "policy_version": activated.policy_version,
                "auto_generated": True,
            },
        )

    def _effective_policy_job(
        self,
        *,
        job: Job,
        active_snapshot: PolicySnapshot | None,
    ) -> Job:
        if active_snapshot is None:
            return job
        policy_spec = job.policy_spec.model_copy(
            update={
                "policy_family": active_snapshot.policy_family,
                "params": {
                    **active_snapshot.payload,
                    "policy_version": active_snapshot.policy_version,
                },
            }
        )
        return job.model_copy(update={"policy_spec": policy_spec})

    def _next_policy_version(
        self,
        *,
        active_snapshot: PolicySnapshot | None,
        effective_job: Job,
    ) -> str:
        if active_snapshot is not None:
            base = active_snapshot.policy_version
        else:
            base_raw = effective_job.policy_spec.params.get("policy_version")
            base = str(base_raw) if base_raw is not None else "v0"

        if base.startswith("v") and base[1:].isdigit():
            return f"v{int(base[1:]) + 1}"

        marker = ".u"
        if marker in base:
            prefix, suffix = base.rsplit(marker, 1)
            if suffix.isdigit():
                return f"{prefix}{marker}{int(suffix) + 1}"

        return f"{base}.u1"

    def _apply_guardrail_action(
        self,
        *,
        workspace_id: str,
        job_id: str,
        action: GuardrailAction | None,
        target_arm_id: str | None,
    ) -> None:
        if action is None or action == GuardrailAction.ANNOTATE:
            return

        if action == GuardrailAction.PAUSE:
            self._repository.set_job_state(
                workspace_id=workspace_id,
                job_id=job_id,
                status=JobStatus.PAUSED,
            )
            return

        if action == GuardrailAction.REQUIRE_MANUAL_RESUME:
            self._repository.set_job_state(
                workspace_id=workspace_id,
                job_id=job_id,
                status=JobStatus.PAUSED,
                approval_state=ApprovalState.PENDING,
            )
            return

        if action in {GuardrailAction.CAP, GuardrailAction.DEMOTE} and target_arm_id is not None:
            self._repository.set_arm_state(
                workspace_id=workspace_id,
                job_id=job_id,
                arm_id=target_arm_id,
                state=ArmState.HELD_OUT,
            )

    def _list_active_jobs(self) -> list[Job]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(JobRow).where(JobRow.status == JobStatus.ACTIVE.value)
            ).all()

        jobs: list[Job] = []
        for row in rows:
            job = self._repository._row_to_job(row)
            if job is not None:
                jobs.append(job)
        return jobs

    def _enqueue_if_missing(self, *, job: Job, task_type: str, due_at: datetime) -> bool:
        with self._session_factory() as session:
            existing = session.scalar(
                select(ScheduledTaskRow).where(
                    ScheduledTaskRow.workspace_id == job.workspace_id,
                    ScheduledTaskRow.job_id == job.job_id,
                    ScheduledTaskRow.task_type == task_type,
                    ScheduledTaskRow.status.in_(["pending", "running"]),
                )
            )
            if existing is not None:
                return False

            session.add(
                ScheduledTaskRow(
                    workspace_id=job.workspace_id,
                    job_id=job.job_id,
                    task_type=task_type,
                    due_at=due_at,
                    status="pending",
                    payload_json={},
                    created_at=now_utc(),
                    updated_at=now_utc(),
                    started_at=None,
                    completed_at=None,
                    attempt_count=0,
                    last_error=None,
                )
            )
            session.commit()
            return True


def _next_policy_due(*, job: Job, now: datetime) -> datetime | None:
    cadence_seconds = job.policy_spec.update_cadence.seconds
    if cadence_seconds is None or cadence_seconds <= 0:
        return None
    return now + timedelta(seconds=cadence_seconds)


def _next_report_due(*, job: Job, now: datetime) -> datetime | None:
    cron = (job.schedule_spec.report_cron or "").strip()
    if cron == "":
        return None

    parts = cron.split()
    if len(parts) != 5 or parts[2:] != ["*", "*", "*"]:
        return None

    minute_raw, hour_raw, _, _, _ = parts
    if not minute_raw.isdigit() or not hour_raw.isdigit():
        return None

    minute = int(minute_raw)
    hour = int(hour_raw)
    if minute not in range(60) or hour not in range(24):
        return None

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _as_aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return now_utc()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def now_utc() -> datetime:
    return datetime.now(tz=UTC)
