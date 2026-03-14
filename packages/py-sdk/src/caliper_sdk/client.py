from __future__ import annotations

import hashlib
import json
from typing import Any, cast

import httpx
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
    JobPatch,
    JobStateTransitionRequest,
    JobStatus,
    OutcomeCreate,
    ReportGenerateRequest,
    ReportPayload,
)
from caliper_policies.engine import AssignmentEngine
from caliper_reports import ReportGenerator
from caliper_storage import SQLRepository, build_engine, init_db, make_session_factory


class ServiceCaliperClient:
    """HTTP client for Caliper service mode APIs."""

    def __init__(
        self,
        *,
        api_url: str = "http://127.0.0.1:8000",
        api_token: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_url = api_url
        self._timeout_seconds = timeout_seconds
        self._headers: dict[str, str] = {}
        if api_token:
            self._headers["Authorization"] = f"Bearer {api_token}"

    def _request(
        self, *, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with httpx.Client(
            base_url=self._api_url,
            timeout=self._timeout_seconds,
            headers=self._headers,
        ) as client:
            response = client.request(method, path, json=payload)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def create_job(self, payload: Job) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/jobs",
            payload=payload.model_dump(mode="json"),
        )

    def get_job(self, *, job_id: str) -> Job:
        body = self._request(method="GET", path=f"/v1/jobs/{job_id}")
        return Job.model_validate(body)

    def update_job(self, *, job_id: str, patch: JobPatch) -> Job:
        body = self._request(
            method="PATCH",
            path=f"/v1/jobs/{job_id}",
            payload=patch.model_dump(mode="json", exclude_none=True),
        )
        return Job.model_validate(body)

    def add_arms(self, *, job_id: str, payload: ArmBulkRegisterRequest) -> ArmBulkRegisterResponse:
        body = self._request(
            method="POST",
            path=f"/v1/jobs/{job_id}/arms:batch_register",
            payload=payload.model_dump(mode="json"),
        )
        return ArmBulkRegisterResponse.model_validate(body)

    def assign(self, payload: AssignRequest) -> AssignResult:
        body = self._request(
            method="POST",
            path="/v1/assign",
            payload=payload.model_dump(mode="json"),
        )
        return AssignResult.model_validate(body)

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate:
        body = self._request(
            method="POST",
            path="/v1/exposures",
            payload=payload.model_dump(mode="json"),
        )
        return ExposureCreate.model_validate(body)

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate:
        body = self._request(
            method="POST",
            path="/v1/outcomes",
            payload=payload.model_dump(mode="json"),
        )
        return OutcomeCreate.model_validate(body)

    def generate_report(self, *, job_id: str, payload: ReportGenerateRequest) -> ReportPayload:
        body = self._request(
            method="POST",
            path=f"/v1/jobs/{job_id}/reports:generate",
            payload=payload.model_dump(mode="json"),
        )
        return ReportPayload.model_validate(body)


class EmbeddedCaliperClient:
    """In-process SDK client backed by local repositories."""

    def __init__(self, *, db_url: str = "sqlite:///./data/caliper-sdk.db") -> None:
        engine = build_engine(db_url)
        init_db(engine)
        self._repository = SQLRepository(make_session_factory(engine))
        self._assignment_engine = AssignmentEngine()
        self._report_generator = ReportGenerator()

    def create_job(self, payload: Job) -> Job:
        return self._repository.create_job(payload)

    def get_job(self, *, job_id: str) -> Job | None:
        return self._repository.get_job(job_id)

    def update_job(self, *, job_id: str, patch: JobPatch) -> Job | None:
        return self._repository.update_job(job_id, patch)

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
        return self._repository.create_exposure(payload)

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate:
        return self._repository.create_outcome(payload)

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
            exposures=len(exposures),
            outcomes=outcomes,
            guardrails=guardrails,
        )
        return self._repository.save_report(generated)
