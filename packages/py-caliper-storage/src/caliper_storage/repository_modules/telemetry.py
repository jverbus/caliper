from __future__ import annotations

from datetime import UTC, datetime

from caliper_core.models import (
    ExposureCreate,
    GuardrailEvent,
    OutcomeCreate,
    PolicySnapshot,
    ReportPayload,
)
from sqlalchemy import select

from caliper_storage.repository_modules.base import SQLRepositoryBase
from caliper_storage.sqlalchemy_models import (
    ExposureRow,
    GuardrailEventRow,
    OutcomeRow,
    PolicySnapshotRow,
    ReportRunRow,
)


class TelemetryRepositoryMixin(SQLRepositoryBase):
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

    def create_guardrail_event(self, event: GuardrailEvent) -> GuardrailEvent:
        with self._session() as session:
            session.add(
                GuardrailEventRow(
                    guardrail_event_id=event.guardrail_event_id,
                    workspace_id=event.workspace_id,
                    job_id=event.job_id,
                    metric=event.metric,
                    status=event.status,
                    action=event.action.value if event.action is not None else None,
                    timestamp=event.timestamp,
                    metadata_json=event.metadata,
                )
            )
        return event

    def list_guardrail_events(self, workspace_id: str, job_id: str) -> list[dict[str, object]]:
        statement = (
            select(GuardrailEventRow)
            .where(
                GuardrailEventRow.workspace_id == workspace_id, GuardrailEventRow.job_id == job_id
            )
            .order_by(GuardrailEventRow.timestamp.asc(), GuardrailEventRow.guardrail_event_id.asc())
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [
                {
                    "guardrail_event_id": row.guardrail_event_id,
                    "metric": row.metric,
                    "status": row.status,
                    "action": row.action,
                    "timestamp": row.timestamp.isoformat(),
                    "metadata": row.metadata_json,
                }
                for row in rows
            ]

    def save_snapshot(self, snapshot: PolicySnapshot) -> PolicySnapshot:
        with self._session() as session:
            session.add(
                PolicySnapshotRow(
                    snapshot_id=snapshot.snapshot_id,
                    workspace_id=snapshot.workspace_id,
                    job_id=snapshot.job_id,
                    policy_family=snapshot.policy_family.value,
                    policy_version=snapshot.policy_version,
                    payload_json=snapshot.payload,
                    is_active=snapshot.is_active,
                    created_at=snapshot.created_at,
                    activated_at=snapshot.activated_at,
                )
            )
        return snapshot

    def list_snapshots(self, workspace_id: str, job_id: str) -> list[PolicySnapshot]:
        statement = (
            select(PolicySnapshotRow)
            .where(
                PolicySnapshotRow.workspace_id == workspace_id,
                PolicySnapshotRow.job_id == job_id,
            )
            .order_by(PolicySnapshotRow.created_at.desc(), PolicySnapshotRow.snapshot_id.desc())
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [self._row_to_policy_snapshot(row) for row in rows]

    def get_snapshot(
        self,
        *,
        workspace_id: str,
        job_id: str,
        snapshot_id: str,
    ) -> PolicySnapshot | None:
        with self._session() as session:
            row = session.get(PolicySnapshotRow, snapshot_id)
            if row is None or row.workspace_id != workspace_id or row.job_id != job_id:
                return None
            return self._row_to_policy_snapshot(row)

    def activate_snapshot(
        self,
        *,
        workspace_id: str,
        job_id: str,
        snapshot_id: str,
    ) -> PolicySnapshot | None:
        with self._session() as session:
            target = session.get(PolicySnapshotRow, snapshot_id)
            if target is None or target.workspace_id != workspace_id or target.job_id != job_id:
                return None

            for row in session.scalars(
                select(PolicySnapshotRow).where(
                    PolicySnapshotRow.workspace_id == workspace_id,
                    PolicySnapshotRow.job_id == job_id,
                    PolicySnapshotRow.is_active.is_(True),
                )
            ).all():
                row.is_active = False
                row.activated_at = None
                session.add(row)

            target.is_active = True
            target.activated_at = datetime.now(tz=UTC)
            session.add(target)
            session.flush()
            return self._row_to_policy_snapshot(target)

    def get_active_snapshot(self, workspace_id: str, job_id: str) -> PolicySnapshot | None:
        statement = (
            select(PolicySnapshotRow)
            .where(
                PolicySnapshotRow.workspace_id == workspace_id,
                PolicySnapshotRow.job_id == job_id,
                PolicySnapshotRow.is_active.is_(True),
            )
            .order_by(PolicySnapshotRow.activated_at.desc(), PolicySnapshotRow.snapshot_id.desc())
        )
        with self._session() as session:
            row = session.scalars(statement).first()
            if row is None:
                return None
            return self._row_to_policy_snapshot(row)

    def save_report(self, report: ReportPayload) -> ReportPayload:
        with self._session() as session:
            session.add(
                ReportRunRow(
                    report_id=report.report_id,
                    workspace_id=report.workspace_id,
                    job_id=report.job_id,
                    generated_at=report.generated_at,
                    payload_json=report.model_dump(mode="json"),
                )
            )
        return report

    def get_latest_report(self, *, workspace_id: str, job_id: str) -> ReportPayload | None:
        statement = (
            select(ReportRunRow)
            .where(ReportRunRow.workspace_id == workspace_id, ReportRunRow.job_id == job_id)
            .order_by(ReportRunRow.generated_at.desc(), ReportRunRow.report_id.desc())
        )
        with self._session() as session:
            row = session.scalars(statement).first()
            if row is None:
                return None
            return ReportPayload.model_validate(row.payload_json)
