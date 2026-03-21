from __future__ import annotations

from typing import Any, cast

import httpx
from caliper_core.models import (
    Arm,
    ArmBulkRegisterRequest,
    ArmBulkRegisterResponse,
    AssignRequest,
    AssignResult,
    ExposureCreate,
    Job,
    JobPatch,
    JobStateTransitionRequest,
    OutcomeCreate,
    ReportGenerateRequest,
    ReportPayload,
)
from caliper_storage import SQLRepository, build_engine, init_db, make_session_factory
from pydantic import ValidationError

from caliper_sdk.service import CaliperService


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
    ) -> Any:
        with httpx.Client(
            base_url=self._api_url,
            timeout=self._timeout_seconds,
            headers=self._headers,
        ) as client:
            response = client.request(method, path, json=payload)
        response.raise_for_status()
        return cast(Any, response.json())

    def create_job(self, payload: Job) -> Job:
        body = self._request(
            method="POST",
            path="/v1/jobs",
            payload=payload.model_dump(mode="json"),
        )
        try:
            return Job.model_validate(body)
        except ValidationError:
            job_id = body.get("job_id") if isinstance(body, dict) else None
            if isinstance(job_id, str) and job_id:
                return self.get_job(job_id=job_id)
            raise

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

    def list_arms(self, *, job_id: str, workspace_id: str) -> list[Arm]:
        body = self._request(
            method="GET",
            path=f"/v1/jobs/{job_id}/arms?workspace_id={workspace_id}",
        )
        return [Arm.model_validate(item) for item in body]

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

    def close(self) -> None:
        return None


class EmbeddedCaliperClient:
    """In-process SDK client backed by local repositories."""

    def __init__(self, *, db_url: str = "sqlite:///./data/caliper-sdk.db") -> None:
        self._engine = build_engine(db_url)
        init_db(self._engine)
        self._repository = SQLRepository(make_session_factory(self._engine))
        self._service = CaliperService(repository=self._repository)

    def close(self) -> None:
        self._engine.dispose()

    def __enter__(self) -> EmbeddedCaliperClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def create_job(self, payload: Job) -> Job:
        return self._service.create_job(payload)

    def get_job(self, *, job_id: str) -> Job:
        job = self._repository.get_job(job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")
        return job

    def update_job(self, *, job_id: str, patch: JobPatch) -> Job | None:
        return self._repository.update_job(job_id, patch)

    def add_arms(self, *, job_id: str, payload: ArmBulkRegisterRequest) -> ArmBulkRegisterResponse:
        return self._service.add_arms(job_id=job_id, payload=payload)

    def list_arms(self, *, job_id: str, workspace_id: str) -> list[Arm]:
        return self._repository.list_arms(workspace_id=workspace_id, job_id=job_id)

    def assign(self, payload: AssignRequest) -> AssignResult:
        return self._service.assign(payload)

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate:
        return self._service.log_exposure(payload)

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate:
        return self._service.log_outcome(payload)

    def pause_job(self, *, job_id: str, payload: JobStateTransitionRequest) -> Job | None:
        return self._service.pause_job(job_id=job_id, payload=payload)

    def resume_job(self, *, job_id: str, payload: JobStateTransitionRequest) -> Job | None:
        return self._service.resume_job(job_id=job_id, payload=payload)

    def generate_report(self, *, job_id: str, payload: ReportGenerateRequest) -> ReportPayload:
        return self._service.generate_report(job_id=job_id, payload=payload)
