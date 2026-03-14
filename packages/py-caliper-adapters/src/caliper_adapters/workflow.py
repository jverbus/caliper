from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from caliper_core.models import (
    AssignRequest,
    AssignResult,
    ExposureCreate,
    ExposureType,
    OutcomeCreate,
    OutcomeEvent,
)


class WorkflowClient(Protocol):
    def assign(self, payload: AssignRequest) -> AssignResult: ...

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate: ...

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate: ...


@dataclass(frozen=True)
class WorkflowAssignment:
    decision_id: str
    arm_id: str
    propensity: float


class WorkflowAdapter:
    """Workflow-facing adapter around core Caliper assignment and event APIs."""

    def __init__(
        self,
        *,
        client: WorkflowClient,
        workspace_id: str,
        job_id: str,
        latency_metric: str = "latency_ms",
        cost_metric: str = "cost_usd",
        acceptance_metric: str = "human_acceptance",
    ) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._job_id = job_id
        self._latency_metric = latency_metric
        self._cost_metric = cost_metric
        self._acceptance_metric = acceptance_metric

    def assign_workflow(
        self,
        *,
        unit_id: str,
        idempotency_key: str,
        candidate_arms: list[str] | None = None,
        context: dict[str, str | int | float | bool] | None = None,
    ) -> WorkflowAssignment:
        decision = self._client.assign(
            AssignRequest(
                workspace_id=self._workspace_id,
                job_id=self._job_id,
                unit_id=unit_id,
                candidate_arms=candidate_arms,
                context=dict(context or {}),
                idempotency_key=idempotency_key,
            )
        )
        self._client.log_exposure(
            ExposureCreate(
                workspace_id=self._workspace_id,
                job_id=self._job_id,
                decision_id=decision.decision_id,
                unit_id=unit_id,
                exposure_type=ExposureType.EXECUTED,
                metadata={"surface": "workflow"},
            )
        )
        return WorkflowAssignment(
            decision_id=decision.decision_id,
            arm_id=decision.arm_id,
            propensity=decision.propensity,
        )

    def log_execution_outcome(
        self,
        *,
        unit_id: str,
        decision_id: str,
        objective_value: float,
        latency_ms: float,
        cost_usd: float,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> OutcomeCreate:
        events = [
            OutcomeEvent(outcome_type="objective", value=objective_value),
            OutcomeEvent(outcome_type=self._latency_metric, value=latency_ms),
            OutcomeEvent(outcome_type=self._cost_metric, value=cost_usd),
        ]
        return self._client.log_outcome(
            OutcomeCreate(
                workspace_id=self._workspace_id,
                job_id=self._job_id,
                decision_id=decision_id,
                unit_id=unit_id,
                events=events,
                metadata={"source": "workflow", **dict(metadata or {})},
            )
        )

    def log_human_acceptance(
        self,
        *,
        unit_id: str,
        decision_id: str,
        accepted: bool,
        reviewed_at: datetime | None = None,
        reviewer: str | None = None,
    ) -> OutcomeCreate:
        reviewed = reviewed_at or datetime.now(tz=UTC)
        metadata: dict[str, str] = {"reviewed_at": reviewed.isoformat()}
        if reviewer is not None:
            metadata["reviewer"] = reviewer
        return self._client.log_outcome(
            OutcomeCreate(
                workspace_id=self._workspace_id,
                job_id=self._job_id,
                decision_id=decision_id,
                unit_id=unit_id,
                events=[
                    OutcomeEvent(
                        outcome_type=self._acceptance_metric,
                        value=1.0 if accepted else 0.0,
                        timestamp=reviewed,
                    )
                ],
                metadata=metadata,
            )
        )
