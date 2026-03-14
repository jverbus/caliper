from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from caliper_core.models import (
    AssignRequest,
    AssignResult,
    ExposureCreate,
    ExposureType,
    OutcomeCreate,
    OutcomeEvent,
)


class WebClient(Protocol):
    def assign(self, payload: AssignRequest) -> AssignResult: ...

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate: ...

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate: ...


@dataclass(frozen=True)
class WebAssignment:
    decision_id: str
    arm_id: str
    propensity: float


class WebAdapter:
    """Web-facing adapter around assignment, exposure, and web outcome logging."""

    def __init__(
        self,
        *,
        client: WebClient,
        workspace_id: str,
        job_id: str,
        click_metric: str = "click",
        conversion_metric: str = "conversion",
    ) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._job_id = job_id
        self._click_metric = click_metric
        self._conversion_metric = conversion_metric

    def assign_request(
        self,
        *,
        unit_id: str,
        idempotency_key: str,
        candidate_arms: list[str] | None = None,
        context: dict[str, str | int | float | bool] | None = None,
    ) -> WebAssignment:
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
        return WebAssignment(
            decision_id=decision.decision_id,
            arm_id=decision.arm_id,
            propensity=decision.propensity,
        )

    def log_render(
        self,
        *,
        unit_id: str,
        decision_id: str,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> ExposureCreate:
        return self._client.log_exposure(
            ExposureCreate(
                workspace_id=self._workspace_id,
                job_id=self._job_id,
                decision_id=decision_id,
                unit_id=unit_id,
                exposure_type=ExposureType.RENDERED,
                metadata={"surface": "web", **dict(metadata or {})},
            )
        )

    def log_click(
        self,
        *,
        unit_id: str,
        decision_id: str,
        value: float = 1.0,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> OutcomeCreate:
        return self._log_single_outcome(
            unit_id=unit_id,
            decision_id=decision_id,
            metric=self._click_metric,
            value=value,
            metadata=metadata,
        )

    def log_conversion(
        self,
        *,
        unit_id: str,
        decision_id: str,
        value: float = 1.0,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> OutcomeCreate:
        return self._log_single_outcome(
            unit_id=unit_id,
            decision_id=decision_id,
            metric=self._conversion_metric,
            value=value,
            metadata=metadata,
        )

    def _log_single_outcome(
        self,
        *,
        unit_id: str,
        decision_id: str,
        metric: str,
        value: float,
        metadata: dict[str, str | int | float | bool] | None,
    ) -> OutcomeCreate:
        return self._client.log_outcome(
            OutcomeCreate(
                workspace_id=self._workspace_id,
                job_id=self._job_id,
                decision_id=decision_id,
                unit_id=unit_id,
                events=[OutcomeEvent(outcome_type=metric, value=value)],
                metadata={"source": "web", **dict(metadata or {})},
            )
        )
