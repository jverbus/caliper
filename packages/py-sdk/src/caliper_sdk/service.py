from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import TypeVar

from caliper_core.events import EventEnvelope
from caliper_core.models import (
    ApprovalState,
    Arm,
    ArmBulkRegisterRequest,
    ArmBulkRegisterResponse,
    AssignRequest,
    AssignResult,
    ExposureCreate,
    Job,
    JobStateTransitionRequest,
    JobStatus,
    OutcomeCreate,
    ReportGenerateRequest,
    ReportPayload,
)
from caliper_policies.engine import AssignmentEngine
from caliper_reports import ReportGenerator
from caliper_storage import SQLRepository

_ResponseT = TypeVar("_ResponseT", ExposureCreate, OutcomeCreate)


class CaliperService:
    """Shared business-logic service for core Caliper lifecycle operations."""

    def __init__(
        self,
        *,
        repository: SQLRepository,
        assignment_engine: AssignmentEngine | None = None,
        report_generator: ReportGenerator | None = None,
    ) -> None:
        self._repository = repository
        self._assignment_engine = assignment_engine or AssignmentEngine()
        self._report_generator = report_generator or ReportGenerator()

    def create_job(self, payload: Job) -> Job:
        return self._repository.create_job(payload)

    def add_arms(self, *, job_id: str, payload: ArmBulkRegisterRequest) -> ArmBulkRegisterResponse:
        registered: list[Arm] = []
        for arm_input in payload.arms:
            registered.append(
                self._repository.upsert_arm(
                    Arm(
                        workspace_id=payload.workspace_id,
                        job_id=job_id,
                        **arm_input.model_dump(mode="python"),
                    )
                )
            )
        return ArmBulkRegisterResponse(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            registered_count=len(registered),
            arms=registered,
        )

    def assign(self, payload: AssignRequest) -> AssignResult:
        request_hash = hashlib.sha256(
            json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        replay = self._repository.get_idempotent_response(
            workspace_id=payload.workspace_id,
            endpoint="/v1/assign",
            idempotency_key=payload.idempotency_key,
        )
        if replay is not None:
            replay_hash, replay_response = replay
            if replay_hash == request_hash:
                return AssignResult.model_validate(replay_response)
            msg = "Idempotency key reused with different payload"
            raise ValueError(msg)

        job = self._repository.get_job(payload.job_id)
        if job is None:
            raise ValueError(f"Job '{payload.job_id}' not found")
        arms = self._repository.list_arms(payload.workspace_id, payload.job_id)
        result = self._assignment_engine.assign(job=job, request=payload, arms=arms)
        saved = self._repository.create_decision(result)
        self._repository.append(
            EventEnvelope(
                workspace_id=saved.workspace_id,
                job_id=saved.job_id,
                event_type="decision.assigned",
                payload=saved.model_dump(mode="json"),
                idempotency_key=payload.idempotency_key,
            )
        )
        self._repository.save_idempotent_response(
            workspace_id=payload.workspace_id,
            endpoint="/v1/assign",
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
            response=saved.model_dump(mode="json"),
        )
        return saved

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate:
        endpoint = "/v1/exposures"
        request_hash = hashlib.sha256(
            json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()

        def _create() -> ExposureCreate:
            decision = self._validate_job_and_decision_context(
                workspace_id=payload.workspace_id,
                job_id=payload.job_id,
                decision_id=payload.decision_id,
                unit_id=payload.unit_id,
            )
            exposure = self._repository.create_exposure(payload)
            self._repository.append(
                EventEnvelope(
                    workspace_id=exposure.workspace_id,
                    job_id=exposure.job_id,
                    event_type="decision.exposed",
                    entity_id=exposure.decision_id,
                    idempotency_key=request_hash,
                    payload={
                        "workspace_id": exposure.workspace_id,
                        "job_id": exposure.job_id,
                        "decision_id": exposure.decision_id,
                        "unit_id": exposure.unit_id,
                        "arm_id": decision.arm_id,
                        "exposure_type": exposure.exposure_type.value,
                        "timestamp": exposure.timestamp.isoformat(),
                        "metadata": exposure.metadata,
                    },
                )
            )
            self._repository.append_audit(
                workspace_id=exposure.workspace_id,
                job_id=exposure.job_id,
                action="decision.exposed",
                metadata={
                    "decision_id": exposure.decision_id,
                    "exposure_type": exposure.exposure_type.value,
                },
            )
            return exposure

        return self._idempotent_create(
            payload=payload,
            endpoint=endpoint,
            request_hash=request_hash,
            model=ExposureCreate,
            create=_create,
        )

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate:
        endpoint = "/v1/outcomes"
        request_hash = hashlib.sha256(
            json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()

        def _create() -> OutcomeCreate:
            decision = self._validate_job_and_decision_context(
                workspace_id=payload.workspace_id,
                job_id=payload.job_id,
                decision_id=payload.decision_id,
                unit_id=payload.unit_id,
            )
            outcome = self._repository.create_outcome(payload)
            self._repository.append(
                EventEnvelope(
                    workspace_id=outcome.workspace_id,
                    job_id=outcome.job_id,
                    event_type="outcome.observed",
                    entity_id=outcome.decision_id,
                    idempotency_key=request_hash,
                    payload={
                        "workspace_id": outcome.workspace_id,
                        "job_id": outcome.job_id,
                        "decision_id": outcome.decision_id,
                        "unit_id": outcome.unit_id,
                        "arm_id": decision.arm_id,
                        "events": [event.model_dump(mode="json") for event in outcome.events],
                        "attribution_window": outcome.attribution_window.model_dump(mode="json"),
                        "metadata": outcome.metadata,
                    },
                )
            )
            self._repository.append_audit(
                workspace_id=outcome.workspace_id,
                job_id=outcome.job_id,
                action="outcome.observed",
                metadata={
                    "decision_id": outcome.decision_id,
                    "event_count": len(outcome.events),
                },
            )
            return outcome

        return self._idempotent_create(
            payload=payload,
            endpoint=endpoint,
            request_hash=request_hash,
            model=OutcomeCreate,
            create=_create,
        )

    def pause_job(self, *, job_id: str, payload: JobStateTransitionRequest) -> Job | None:
        return self._repository.set_job_state(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            status=JobStatus.PAUSED,
            approval_state=payload.approval_state,
        )

    def resume_job(self, *, job_id: str, payload: JobStateTransitionRequest) -> Job | None:
        approval_state = payload.approval_state or ApprovalState.APPROVED
        return self._repository.set_job_state(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            status=JobStatus.ACTIVE,
            approval_state=approval_state,
        )

    def generate_report(self, *, job_id: str, payload: ReportGenerateRequest) -> ReportPayload:
        job = self._repository.get_job(job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")
        arms = self._repository.list_arms(payload.workspace_id, job_id)
        decisions = self._repository.list_decisions(payload.workspace_id, job_id)
        exposures = self._repository.list_exposures(payload.workspace_id, job_id)
        outcomes = self._repository.list_outcomes(payload.workspace_id, job_id)
        guardrails = self._repository.list_guardrail_events(payload.workspace_id, job_id)
        generated = self._report_generator.generate(
            job=job,
            arms=arms,
            decisions=decisions,
            exposures=exposures,
            outcomes=outcomes,
            guardrails=guardrails,
        )
        return self._repository.save_report(generated)

    def _idempotent_create(
        self,
        *,
        payload: ExposureCreate | OutcomeCreate,
        endpoint: str,
        request_hash: str,
        model: type[_ResponseT],
        create: Callable[[], _ResponseT],
    ) -> _ResponseT:
        cached = self._repository.get_idempotent_response(
            workspace_id=payload.workspace_id,
            endpoint=endpoint,
            idempotency_key=request_hash,
        )
        if cached is not None:
            _, response = cached
            return model.model_validate(response)

        created = create()
        self._repository.save_idempotent_response(
            workspace_id=payload.workspace_id,
            endpoint=endpoint,
            idempotency_key=request_hash,
            request_hash=request_hash,
            response=created.model_dump(mode="json"),
        )
        return created

    def _validate_job_and_decision_context(
        self,
        *,
        workspace_id: str,
        job_id: str,
        decision_id: str,
        unit_id: str,
    ) -> AssignResult:
        job = self._repository.get_job(job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")
        if workspace_id != job.workspace_id:
            raise ValueError("workspace_id does not match the job workspace")

        decision = self._repository.get_decision(decision_id)
        if decision is None:
            raise ValueError(f"Decision '{decision_id}' not found")
        if (
            decision.workspace_id != workspace_id
            or decision.job_id != job_id
            or decision.unit_id != unit_id
        ):
            raise ValueError("Decision context does not match workspace_id/job_id/unit_id")
        return decision
