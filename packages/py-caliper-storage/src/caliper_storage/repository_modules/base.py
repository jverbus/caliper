from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from caliper_core.events import EventEnvelope
from caliper_core.models import (
    Arm,
    AssignResult,
    ExposureCreate,
    Job,
    OutcomeCreate,
    PolicySnapshot,
)
from sqlalchemy.orm import Session

from caliper_storage.sqlalchemy_models import (
    ArmRow,
    DecisionRow,
    EventRow,
    ExposureRow,
    JobRow,
    OutcomeRow,
    PolicySnapshotRow,
)

SessionFactory = Callable[[], Session]


class SQLRepositoryBase:
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

    def _row_to_policy_snapshot(self, row: PolicySnapshotRow) -> PolicySnapshot:
        return PolicySnapshot.model_validate(
            {
                "snapshot_id": row.snapshot_id,
                "workspace_id": row.workspace_id,
                "job_id": row.job_id,
                "policy_family": row.policy_family,
                "policy_version": row.policy_version,
                "payload": row.payload_json,
                "is_active": row.is_active,
                "created_at": row.created_at,
                "activated_at": row.activated_at,
            }
        )

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
