from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from caliper_core.models import (
    AssignRequest,
    AssignResult,
    ExposureCreate,
    ExposureType,
    OutcomeCreate,
    OutcomeEvent,
)


class OrgRouterClient(Protocol):
    def assign(self, payload: AssignRequest) -> AssignResult: ...

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate: ...

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate: ...


@dataclass(frozen=True)
class OrganizationRoute:
    decision_id: str
    arm_id: str
    propensity: float
    policy_version: str
    child_policy_ref: str | None = None


class OrgRouterAdapter:
    """Organization-router adapter for cluster/topology routing flows."""

    def __init__(
        self,
        *,
        client: OrgRouterClient,
        workspace_id: str,
        job_id: str,
        child_policy_refs: dict[str, str] | None = None,
        latency_metric: str = "latency_ms",
        cost_metric: str = "cost_usd",
    ) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._job_id = job_id
        self._child_policy_refs = dict(child_policy_refs or {})
        self._latency_metric = latency_metric
        self._cost_metric = cost_metric

    def route_task(
        self,
        *,
        unit_id: str,
        idempotency_key: str,
        candidate_arms: list[str] | None = None,
        context: dict[str, str | int | float | bool] | None = None,
    ) -> OrganizationRoute:
        assign_payload = AssignRequest(
            workspace_id=self._workspace_id,
            job_id=self._job_id,
            unit_id=unit_id,
            candidate_arms=candidate_arms,
            context={"surface": "org_router", **dict(context or {})},
            idempotency_key=idempotency_key,
        )
        decision = self._client.assign(assign_payload)
        self._client.log_exposure(
            ExposureCreate(
                workspace_id=self._workspace_id,
                job_id=self._job_id,
                decision_id=decision.decision_id,
                unit_id=unit_id,
                exposure_type=ExposureType.EXECUTED,
                metadata={"surface": "org_router", "organization_arm_id": decision.arm_id},
            )
        )
        return OrganizationRoute(
            decision_id=decision.decision_id,
            arm_id=decision.arm_id,
            propensity=decision.propensity,
            policy_version=decision.policy_version,
            child_policy_ref=self._child_policy_refs.get(decision.arm_id),
        )

    def log_task_completion(
        self,
        *,
        unit_id: str,
        decision_id: str,
        objective_value: float,
        latency_ms: float,
        cost_usd: float,
        metadata: dict[str, str | int | float | bool] | None = None,
        downstream_events: list[OutcomeEvent] | None = None,
    ) -> OutcomeCreate:
        events = [
            OutcomeEvent(outcome_type="objective", value=objective_value),
            OutcomeEvent(outcome_type=self._latency_metric, value=latency_ms),
            OutcomeEvent(outcome_type=self._cost_metric, value=cost_usd),
            *(downstream_events or []),
        ]
        outcome_metadata: dict[str, Any] = {"source": "org_router", **dict(metadata or {})}
        return self._client.log_outcome(
            OutcomeCreate(
                workspace_id=self._workspace_id,
                job_id=self._job_id,
                decision_id=decision_id,
                unit_id=unit_id,
                events=events,
                metadata=outcome_metadata,
            )
        )
