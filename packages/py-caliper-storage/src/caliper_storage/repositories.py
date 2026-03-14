from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from caliper_core.events import EventEnvelope
from caliper_core.interfaces import (
    ArmRepository,
    AuditRepository,
    DecisionRepository,
    EventLedger,
    ExposureRepository,
    JobRepository,
    OutcomeRepository,
)
from caliper_core.models import (
    ApprovalState,
    Arm,
    ArmState,
    AssignResult,
    AuditRecord,
    ExposureCreate,
    Job,
    JobPatch,
    JobStatus,
    OutcomeCreate,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from caliper_storage.sqlalchemy_models import (
    ArmRow,
    AuditRow,
    DecisionRow,
    EventRow,
    ExposureRow,
    JobRow,
    OutcomeRow,
    ProjectionMetricRow,
    ProjectionRebuildAuditRow,
)

SessionFactory = Callable[[], Session]


class SQLRepository(
    JobRepository,
    ArmRepository,
    DecisionRepository,
    ExposureRepository,
    OutcomeRepository,
    EventLedger,
    AuditRepository,
):
    """SQLAlchemy-backed repository implementation for core domain models."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

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

    def upsert_arm(self, arm: Arm) -> Arm:
        with self._session() as session:
            row = session.get(ArmRow, arm.arm_id)
            if row is None:
                row = ArmRow(
                    arm_id=arm.arm_id,
                    job_id=arm.job_id,
                    workspace_id=arm.workspace_id,
                    name=arm.name,
                    arm_type=arm.arm_type.value,
                    payload_ref=arm.payload_ref,
                    metadata_json=arm.metadata,
                    state=arm.state.value,
                    created_at=arm.created_at,
                    updated_at=arm.updated_at,
                )
            else:
                row.workspace_id = arm.workspace_id
                row.job_id = arm.job_id
                row.name = arm.name
                row.arm_type = arm.arm_type.value
                row.payload_ref = arm.payload_ref
                row.metadata_json = arm.metadata
                row.state = arm.state.value
                row.updated_at = datetime.now(tz=UTC)

            session.add(row)
        return arm

    def get_arm(self, arm_id: str) -> Arm | None:
        with self._session() as session:
            row = session.get(ArmRow, arm_id)
            if row is None:
                return None
            return self._row_to_arm(row)

    def list_arms(self, workspace_id: str, job_id: str) -> list[Arm]:
        statement = (
            select(ArmRow)
            .where(ArmRow.workspace_id == workspace_id, ArmRow.job_id == job_id)
            .order_by(ArmRow.created_at.asc())
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [self._row_to_arm(row) for row in rows]

    def set_arm_state(
        self,
        *,
        workspace_id: str,
        job_id: str,
        arm_id: str,
        state: ArmState,
    ) -> Arm | None:
        with self._session() as session:
            row = session.get(ArmRow, arm_id)
            if row is None or row.workspace_id != workspace_id or row.job_id != job_id:
                return None
            row.state = state.value
            row.updated_at = datetime.now(tz=UTC)
            session.add(row)
            session.flush()
            return self._row_to_arm(row)

    def create_decision(self, decision: AssignResult) -> AssignResult:
        row = DecisionRow(
            decision_id=decision.decision_id,
            workspace_id=decision.workspace_id,
            job_id=decision.job_id,
            unit_id=decision.unit_id,
            arm_id=decision.arm_id,
            propensity=decision.propensity,
            policy_family=decision.policy_family.value,
            policy_version=decision.policy_version,
            context_schema_version=decision.context_schema_version,
            diagnostics_json=decision.diagnostics.model_dump(mode="json"),
            candidate_arms_json=decision.candidate_arms,
            context_json=decision.context,
            timestamp=decision.timestamp,
        )
        with self._session() as session:
            session.add(row)
        return decision

    def get_decision(self, decision_id: str) -> AssignResult | None:
        with self._session() as session:
            row = session.get(DecisionRow, decision_id)
            return self._row_to_decision(row)

    def create_exposure(self, exposure: ExposureCreate) -> ExposureCreate:
        row = ExposureRow(
            workspace_id=exposure.workspace_id,
            job_id=exposure.job_id,
            decision_id=exposure.decision_id,
            unit_id=exposure.unit_id,
            exposure_type=exposure.exposure_type.value,
            timestamp=exposure.timestamp,
            metadata_json=exposure.metadata,
        )
        with self._session() as session:
            session.add(row)
        return exposure

    def list_exposures(self, workspace_id: str, job_id: str) -> list[ExposureCreate]:
        statement = (
            select(ExposureRow)
            .where(ExposureRow.workspace_id == workspace_id, ExposureRow.job_id == job_id)
            .order_by(ExposureRow.timestamp.asc(), ExposureRow.exposure_id.asc())
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [self._row_to_exposure(row) for row in rows]

    def create_outcome(self, outcome: OutcomeCreate) -> OutcomeCreate:
        row = OutcomeRow(
            workspace_id=outcome.workspace_id,
            job_id=outcome.job_id,
            decision_id=outcome.decision_id,
            unit_id=outcome.unit_id,
            events_json=[event.model_dump(mode="json") for event in outcome.events],
            attribution_window_json=outcome.attribution_window.model_dump(mode="json"),
            metadata_json=outcome.metadata,
        )
        with self._session() as session:
            session.add(row)
        return outcome

    def list_outcomes(self, workspace_id: str, job_id: str) -> list[OutcomeCreate]:
        statement = (
            select(OutcomeRow)
            .where(OutcomeRow.workspace_id == workspace_id, OutcomeRow.job_id == job_id)
            .order_by(OutcomeRow.outcome_id.asc())
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [self._row_to_outcome(row) for row in rows]

    def append(self, event: EventEnvelope) -> EventEnvelope:
        with self._session() as session:
            if event.idempotency_key is not None:
                existing = session.scalar(
                    select(EventRow).where(
                        EventRow.workspace_id == event.workspace_id,
                        EventRow.job_id == event.job_id,
                        EventRow.event_type == event.event_type,
                        EventRow.idempotency_key == event.idempotency_key,
                    )
                )
                if existing is not None:
                    return self._row_to_event(existing)

            row = EventRow(
                event_id=event.event_id,
                workspace_id=event.workspace_id,
                job_id=event.job_id,
                event_type=event.event_type,
                entity_id=event.entity_id,
                idempotency_key=event.idempotency_key,
                timestamp=event.timestamp,
                payload_json=event.payload,
            )
            session.add(row)
            return event

    def replay(
        self,
        *,
        workspace_id: str,
        job_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[EventEnvelope]:
        statement = select(EventRow).where(
            EventRow.workspace_id == workspace_id,
            EventRow.job_id == job_id,
        )
        if start is not None:
            statement = statement.where(EventRow.timestamp >= start)
        if end is not None:
            statement = statement.where(EventRow.timestamp <= end)

        statement = statement.order_by(EventRow.timestamp.asc(), EventRow.event_id.asc())

        with self._session() as session:
            rows = session.scalars(statement).all()
            return [self._row_to_event(row) for row in rows]

    def replace_projection_metrics(
        self,
        *,
        workspace_id: str,
        job_id: str,
        metrics: dict[str, dict[str, int]],
    ) -> None:
        with self._session() as session:
            session.execute(
                delete(ProjectionMetricRow).where(
                    ProjectionMetricRow.workspace_id == workspace_id,
                    ProjectionMetricRow.job_id == job_id,
                )
            )
            for arm_id, counts in metrics.items():
                session.add(
                    ProjectionMetricRow(
                        workspace_id=workspace_id,
                        job_id=job_id,
                        arm_id=arm_id,
                        assignments=counts.get("assignments", 0),
                        exposures=counts.get("exposures", 0),
                        outcomes=counts.get("outcomes", 0),
                    )
                )

    def list_projection_metrics(
        self, *, workspace_id: str, job_id: str
    ) -> list[ProjectionMetricRow]:
        statement = (
            select(ProjectionMetricRow)
            .where(
                ProjectionMetricRow.workspace_id == workspace_id,
                ProjectionMetricRow.job_id == job_id,
            )
            .order_by(ProjectionMetricRow.arm_id.asc())
        )
        with self._session() as session:
            return list(session.scalars(statement).all())

    def record_projection_rebuild(
        self,
        *,
        workspace_id: str,
        job_id: str,
        event_count: int,
        start: datetime | None,
        end: datetime | None,
    ) -> str:
        rebuild_id = f"prj_{uuid4().hex[:12]}"
        with self._session() as session:
            session.add(
                ProjectionRebuildAuditRow(
                    rebuild_id=rebuild_id,
                    workspace_id=workspace_id,
                    job_id=job_id,
                    rebuilt_at=datetime.now(tz=UTC),
                    event_count=event_count,
                    start_timestamp=start,
                    end_timestamp=end,
                )
            )
        return rebuild_id

    def list_projection_rebuild_audits(
        self, *, workspace_id: str, job_id: str
    ) -> list[ProjectionRebuildAuditRow]:
        statement = (
            select(ProjectionRebuildAuditRow)
            .where(
                ProjectionRebuildAuditRow.workspace_id == workspace_id,
                ProjectionRebuildAuditRow.job_id == job_id,
            )
            .order_by(ProjectionRebuildAuditRow.rebuilt_at.desc())
        )
        with self._session() as session:
            return list(session.scalars(statement).all())

    def _row_to_job(self, row: JobRow | None) -> Job | None:
        if row is None:
            return None
        return Job.model_validate(
            {
                "job_id": row.job_id,
                "workspace_id": row.workspace_id,
                "name": row.name,
                "surface_type": row.surface_type,
                "status": row.status,
                "approval_state": row.approval_state,
                "objective_spec": row.objective_spec,
                "guardrail_spec": row.guardrail_spec,
                "policy_spec": row.policy_spec,
                "segment_spec": row.segment_spec,
                "schedule_spec": row.schedule_spec,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )

    def _row_to_arm(self, row: ArmRow) -> Arm:
        return Arm.model_validate(
            {
                "arm_id": row.arm_id,
                "workspace_id": row.workspace_id,
                "job_id": row.job_id,
                "name": row.name,
                "arm_type": row.arm_type,
                "payload_ref": row.payload_ref,
                "metadata": row.metadata_json,
                "state": row.state,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )

    def _row_to_decision(self, row: DecisionRow | None) -> AssignResult | None:
        if row is None:
            return None
        return AssignResult.model_validate(
            {
                "decision_id": row.decision_id,
                "workspace_id": row.workspace_id,
                "job_id": row.job_id,
                "unit_id": row.unit_id,
                "arm_id": row.arm_id,
                "propensity": row.propensity,
                "policy_family": row.policy_family,
                "policy_version": row.policy_version,
                "context_schema_version": row.context_schema_version,
                "diagnostics": row.diagnostics_json,
                "candidate_arms": row.candidate_arms_json,
                "context": row.context_json,
                "timestamp": row.timestamp,
            }
        )

    def _row_to_exposure(self, row: ExposureRow) -> ExposureCreate:
        return ExposureCreate.model_validate(
            {
                "workspace_id": row.workspace_id,
                "job_id": row.job_id,
                "decision_id": row.decision_id,
                "unit_id": row.unit_id,
                "exposure_type": row.exposure_type,
                "timestamp": row.timestamp,
                "metadata": row.metadata_json,
            }
        )

    def _row_to_outcome(self, row: OutcomeRow) -> OutcomeCreate:
        return OutcomeCreate.model_validate(
            {
                "workspace_id": row.workspace_id,
                "job_id": row.job_id,
                "decision_id": row.decision_id,
                "unit_id": row.unit_id,
                "events": row.events_json,
                "attribution_window": row.attribution_window_json,
                "metadata": row.metadata_json,
            }
        )

    def _row_to_event(self, row: EventRow) -> EventEnvelope:
        return EventEnvelope.model_validate(
            {
                "event_id": row.event_id,
                "workspace_id": row.workspace_id,
                "job_id": row.job_id,
                "event_type": row.event_type,
                "entity_id": row.entity_id,
                "idempotency_key": row.idempotency_key,
                "timestamp": row.timestamp,
                "payload": row.payload_json,
            }
        )


class SQLiteRepository(SQLRepository):
    """SQLite-specific repository facade backed by SQLRepository."""


class PostgresRepository(SQLRepository):
    """Postgres-specific repository facade backed by SQLRepository."""
