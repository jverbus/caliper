from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from caliper_core.models import Job, JobStatus
from caliper_reports import ReportGenerator
from caliper_reward.engine import RewardEngine
from caliper_storage import SQLRepository
from caliper_storage.sqlalchemy_models import JobRow, ScheduledTaskRow
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class WorkerRunResult:
    scheduled: int = 0
    executed: int = 0


class WorkerLoop:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._repository = SQLRepository(session_factory)
        self._report_generator = ReportGenerator()
        self._reward_engine = RewardEngine()

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
        try:
            if task.task_type == "generate_report":
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
            exposures=len(exposures),
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

        decisions = self._repository.list_decisions(workspace_id, job_id)
        outcomes = self._repository.list_outcomes(workspace_id, job_id)
        dataset = self._reward_engine.build_policy_update_dataset(
            objective_spec=job.objective_spec,
            decisions=decisions,
            outcomes=outcomes,
        )
        self._repository.append_audit(
            workspace_id,
            job_id,
            "worker.policy.updated",
            {"record_count": len(dataset)},
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
