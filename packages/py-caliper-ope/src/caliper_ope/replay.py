from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from caliper_core.models import ExposureCreate, OutcomeCreate
from caliper_storage.repositories import SQLRepository


@dataclass(frozen=True)
class ReplayRecord:
    workspace_id: str
    job_id: str
    decision_id: str
    unit_id: str
    chosen_action: str
    propensity: float
    reward: float
    context: dict[str, object]
    assigned_at: datetime
    first_exposed_at: datetime | None
    latest_outcome_at: datetime | None


class ReplayExporter:
    """Build replay datasets suitable for OPE experiments."""

    def __init__(self, repository: SQLRepository) -> None:
        self._repository = repository

    def export(self, *, workspace_id: str, job_id: str) -> list[ReplayRecord]:
        decisions = self._repository.list_decisions(workspace_id=workspace_id, job_id=job_id)
        exposures = self._repository.list_exposures(workspace_id=workspace_id, job_id=job_id)
        outcomes = self._repository.list_outcomes(workspace_id=workspace_id, job_id=job_id)

        first_exposure_by_decision = self._index_first_exposure(exposures)
        reward_by_decision, latest_outcome_by_decision = self._index_outcomes(outcomes)

        rows: list[ReplayRecord] = []
        for decision in decisions:
            rows.append(
                ReplayRecord(
                    workspace_id=decision.workspace_id,
                    job_id=decision.job_id,
                    decision_id=decision.decision_id,
                    unit_id=decision.unit_id,
                    chosen_action=decision.arm_id,
                    propensity=decision.propensity,
                    reward=reward_by_decision.get(decision.decision_id, 0.0),
                    context=dict(decision.context),
                    assigned_at=decision.timestamp,
                    first_exposed_at=first_exposure_by_decision.get(decision.decision_id),
                    latest_outcome_at=latest_outcome_by_decision.get(decision.decision_id),
                )
            )

        return rows

    @staticmethod
    def _index_first_exposure(exposures: list[ExposureCreate]) -> dict[str, datetime]:
        indexed: dict[str, datetime] = {}
        for exposure in exposures:
            existing = indexed.get(exposure.decision_id)
            if existing is None or exposure.timestamp < existing:
                indexed[exposure.decision_id] = exposure.timestamp
        return indexed

    @staticmethod
    def _index_outcomes(
        outcomes: list[OutcomeCreate],
    ) -> tuple[dict[str, float], dict[str, datetime]]:
        reward_by_decision: dict[str, float] = {}
        latest_outcome_by_decision: dict[str, datetime] = {}

        for outcome in outcomes:
            reward = reward_by_decision.get(outcome.decision_id, 0.0)
            latest = latest_outcome_by_decision.get(outcome.decision_id)
            for event in outcome.events:
                reward += event.value
                if latest is None or event.timestamp > latest:
                    latest = event.timestamp
            reward_by_decision[outcome.decision_id] = reward
            if latest is not None:
                latest_outcome_by_decision[outcome.decision_id] = latest

        return reward_by_decision, latest_outcome_by_decision
