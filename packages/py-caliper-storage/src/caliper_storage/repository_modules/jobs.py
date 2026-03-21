from __future__ import annotations

from datetime import UTC, datetime

from caliper_core.models import ApprovalState, AuditRecord, Job, JobPatch, JobStatus
from sqlalchemy import select

from caliper_storage.repository_modules.base import SQLRepositoryBase
from caliper_storage.sqlalchemy_models import AuditRow, JobRow


class JobAuditRepositoryMixin(SQLRepositoryBase):
    def create_job(self, job: Job) -> Job:
        row = JobRow(
            job_id=job.job_id,
            workspace_id=job.workspace_id,
            name=job.name,
            surface_type=job.surface_type.value,
            status=job.status.value,
            approval_state=job.approval_state.value,
            objective_spec=job.objective_spec.model_dump(mode="json"),
            guardrail_spec=job.guardrail_spec.model_dump(mode="json"),
            policy_spec=job.policy_spec.model_dump(mode="json"),
            segment_spec=job.segment_spec.model_dump(mode="json"),
            schedule_spec=job.schedule_spec.model_dump(mode="json"),
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        with self._session() as session:
            session.add(row)
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._session() as session:
            row = session.get(JobRow, job_id)
            return self._row_to_job(row)

    def list_jobs(self, *, workspace_id: str | None = None) -> list[Job]:
        statement = select(JobRow).order_by(JobRow.created_at.asc(), JobRow.job_id.asc())
        if workspace_id is not None:
            statement = statement.where(JobRow.workspace_id == workspace_id)
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [job for row in rows if (job := self._row_to_job(row)) is not None]

    def update_job(self, job_id: str, patch: JobPatch) -> Job | None:
        with self._session() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return None

            if patch.name is not None:
                row.name = patch.name
            if patch.objective_spec is not None:
                row.objective_spec = patch.objective_spec.model_dump(mode="json")
            if patch.guardrail_spec is not None:
                row.guardrail_spec = patch.guardrail_spec.model_dump(mode="json")
            if patch.policy_spec is not None:
                row.policy_spec = patch.policy_spec.model_dump(mode="json")
            if patch.segment_spec is not None:
                row.segment_spec = patch.segment_spec.model_dump(mode="json")
            if patch.schedule_spec is not None:
                row.schedule_spec = patch.schedule_spec.model_dump(mode="json")
            row.updated_at = datetime.now(tz=UTC)

            session.add(row)
            session.flush()
            return self._row_to_job(row)

    def set_job_state(
        self,
        *,
        workspace_id: str,
        job_id: str,
        status: JobStatus,
        approval_state: ApprovalState | None = None,
    ) -> Job | None:
        with self._session() as session:
            row = session.get(JobRow, job_id)
            if row is None or row.workspace_id != workspace_id:
                return None
            row.status = status.value
            if approval_state is not None:
                row.approval_state = approval_state.value
            row.updated_at = datetime.now(tz=UTC)
            session.add(row)
            session.flush()
            return self._row_to_job(row)

    def append_audit(
        self,
        workspace_id: str,
        job_id: str,
        action: str,
        metadata: dict[str, object],
    ) -> None:
        with self._session() as session:
            session.add(
                AuditRow(
                    workspace_id=workspace_id,
                    job_id=job_id,
                    action=action,
                    timestamp=datetime.now(tz=UTC),
                    metadata_json=metadata,
                )
            )

    def list_audit(self, *, workspace_id: str, job_id: str) -> list[AuditRecord]:
        statement = (
            select(AuditRow)
            .where(AuditRow.workspace_id == workspace_id, AuditRow.job_id == job_id)
            .order_by(AuditRow.timestamp.asc(), AuditRow.audit_id.asc())
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [
                AuditRecord(action=row.action, timestamp=row.timestamp, metadata=row.metadata_json)
                for row in rows
            ]
