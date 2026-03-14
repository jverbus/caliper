from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from caliper_core.events import EventEnvelope
from caliper_core.models import (
    Arm,
    AssignResult,
    ExposureCreate,
    GuardrailEvent,
    Job,
    JobPatch,
    OutcomeCreate,
    PolicySnapshot,
)


@runtime_checkable
class JobRepository(Protocol):
    def create_job(self, job: Job) -> Job: ...

    def get_job(self, job_id: str) -> Job | None: ...

    def update_job(self, job_id: str, patch: JobPatch) -> Job | None: ...


@runtime_checkable
class ArmRepository(Protocol):
    def upsert_arm(self, arm: Arm) -> Arm: ...

    def list_arms(self, workspace_id: str, job_id: str) -> list[Arm]: ...


@runtime_checkable
class DecisionRepository(Protocol):
    def create_decision(self, decision: AssignResult) -> AssignResult: ...

    def get_decision(self, decision_id: str) -> AssignResult | None: ...


@runtime_checkable
class ExposureRepository(Protocol):
    def create_exposure(self, exposure: ExposureCreate) -> ExposureCreate: ...

    def list_exposures(self, workspace_id: str, job_id: str) -> list[ExposureCreate]: ...


@runtime_checkable
class OutcomeRepository(Protocol):
    def create_outcome(self, outcome: OutcomeCreate) -> OutcomeCreate: ...

    def list_outcomes(self, workspace_id: str, job_id: str) -> list[OutcomeCreate]: ...


@runtime_checkable
class GuardrailEventRepository(Protocol):
    def create_guardrail_event(self, event: GuardrailEvent) -> GuardrailEvent: ...


@runtime_checkable
class PolicySnapshotRepository(Protocol):
    def save_snapshot(self, snapshot: PolicySnapshot) -> PolicySnapshot: ...

    def get_active_snapshot(self, workspace_id: str, job_id: str) -> PolicySnapshot | None: ...


@runtime_checkable
class AuditRepository(Protocol):
    def append_audit(
        self,
        workspace_id: str,
        job_id: str,
        action: str,
        metadata: dict[str, object],
    ) -> None: ...


@runtime_checkable
class EventLedger(Protocol):
    def append(self, event: EventEnvelope) -> EventEnvelope: ...

    def replay(
        self,
        *,
        workspace_id: str,
        job_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[EventEnvelope]: ...


@runtime_checkable
class EventBus(Protocol):
    def publish(self, event: EventEnvelope) -> None: ...
