from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from caliper_core.events import EventEnvelope
from sqlalchemy import delete, select

from caliper_storage.repository_modules.base import SQLRepositoryBase
from caliper_storage.sqlalchemy_models import (
    EventRow,
    ProjectionMetricRow,
    ProjectionRebuildAuditRow,
)


class EventProjectionRepositoryMixin(SQLRepositoryBase):
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
