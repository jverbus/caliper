from __future__ import annotations

from typing import Annotated

from api.dependencies import (
    get_engine,
    get_repository,
    health_check,
    readiness_check,
    require_api_token,
)
from caliper_core.models import Job, JobCreate, JobCreateResponse, JobPatch
from caliper_storage import SQLRepository
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import Engine


def create_app() -> FastAPI:
    app = FastAPI(title="Caliper API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return health_check()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return health_check()

    @app.get("/readyz")
    def readyz(engine: Annotated[Engine, Depends(get_engine)]) -> dict[str, str]:
        return readiness_check(engine)

    @app.get("/v1/system/info", dependencies=[Depends(require_api_token)])
    def system_info() -> dict[str, str]:
        return {"service": "caliper-api", "api_version": "v1"}

    @app.post(
        "/v1/jobs",
        dependencies=[Depends(require_api_token)],
        response_model=JobCreateResponse,
    )
    def create_job(
        payload: JobCreate,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> JobCreateResponse:
        created = repository.create_job(Job(**payload.model_dump()))
        repository.append_audit(
            workspace_id=created.workspace_id,
            job_id=created.job_id,
            action="job.create",
            metadata={"status": created.status.value},
        )
        return JobCreateResponse(
            job_id=created.job_id,
            status=created.status,
            created_at=created.created_at,
        )

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_api_token)], response_model=Job)
    def get_job(
        job_id: str,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> Job:
        job = repository.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        return job

    @app.patch("/v1/jobs/{job_id}", dependencies=[Depends(require_api_token)], response_model=Job)
    def update_job(
        job_id: str,
        patch: JobPatch,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> Job:
        updated = repository.update_job(job_id, patch)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        repository.append_audit(
            workspace_id=updated.workspace_id,
            job_id=updated.job_id,
            action="job.update",
            metadata={"patched_fields": sorted(patch.model_dump(exclude_none=True).keys())},
        )
        return updated

    return app


app = create_app()
