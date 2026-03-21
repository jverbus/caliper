from __future__ import annotations

from datetime import UTC, datetime

from caliper_core.models import Arm, ArmState, AssignResult
from sqlalchemy import select

from caliper_storage.repository_modules.base import SQLRepositoryBase
from caliper_storage.sqlalchemy_models import ArmRow, DecisionRow, IdempotencyKeyRow


class ArmDecisionRepositoryMixin(SQLRepositoryBase):
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

    def list_decisions(self, workspace_id: str, job_id: str) -> list[AssignResult]:
        statement = (
            select(DecisionRow)
            .where(DecisionRow.workspace_id == workspace_id, DecisionRow.job_id == job_id)
            .order_by(DecisionRow.timestamp.asc(), DecisionRow.decision_id.asc())
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [
                decision for row in rows if (decision := self._row_to_decision(row)) is not None
            ]

    def get_idempotent_response(
        self,
        *,
        workspace_id: str,
        endpoint: str,
        idempotency_key: str,
    ) -> tuple[str, dict[str, object]] | None:
        statement = select(IdempotencyKeyRow).where(
            IdempotencyKeyRow.workspace_id == workspace_id,
            IdempotencyKeyRow.endpoint == endpoint,
            IdempotencyKeyRow.idempotency_key == idempotency_key,
        )
        with self._session() as session:
            row = session.scalar(statement)
            if row is None:
                return None
            return row.request_hash, row.response_json

    def save_idempotent_response(
        self,
        *,
        workspace_id: str,
        endpoint: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, object],
    ) -> None:
        with self._session() as session:
            existing = session.scalar(
                select(IdempotencyKeyRow).where(
                    IdempotencyKeyRow.workspace_id == workspace_id,
                    IdempotencyKeyRow.endpoint == endpoint,
                    IdempotencyKeyRow.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return
            session.add(
                IdempotencyKeyRow(
                    workspace_id=workspace_id,
                    endpoint=endpoint,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_json=response,
                    created_at=datetime.now(tz=UTC),
                )
            )
