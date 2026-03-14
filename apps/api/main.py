from __future__ import annotations

from typing import Annotated

from api.dependencies import (
    get_engine,
    get_repository,
    health_check,
    readiness_check,
    require_api_token,
)
from caliper_core.models import (
    ApprovalState,
    Arm,
    ArmBulkRegisterRequest,
    ArmBulkRegisterResponse,
    ArmLifecycleAction,
    ArmLifecycleRequest,
    ArmState,
    AuditRecord,
    Job,
    JobCreate,
    JobCreateResponse,
    JobPatch,
    JobStateTransitionRequest,
    JobStatus,
)
from caliper_storage import SQLRepository
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import Engine

_JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.DRAFT: {JobStatus.SHADOW, JobStatus.ACTIVE, JobStatus.ARCHIVED},
    JobStatus.SHADOW: {JobStatus.ACTIVE, JobStatus.PAUSED, JobStatus.ARCHIVED},
    JobStatus.ACTIVE: {JobStatus.PAUSED, JobStatus.COMPLETED, JobStatus.ARCHIVED},
    JobStatus.PAUSED: {JobStatus.ACTIVE, JobStatus.COMPLETED, JobStatus.ARCHIVED},
    JobStatus.COMPLETED: {JobStatus.ARCHIVED},
    JobStatus.ARCHIVED: set(),
}


def _transition_job_state(
    *,
    repository: SQLRepository,
    job_id: str,
    payload: JobStateTransitionRequest,
    target_state: JobStatus,
    action_name: str,
) -> Job:
    job = repository.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    if payload.workspace_id != job.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workspace_id does not match the job workspace.",
        )
    if target_state not in _JOB_TRANSITIONS[job.status]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invalid job state transition: {job.status.value} -> {target_state.value}."
            ),
        )

    updated = repository.set_job_state(
        workspace_id=payload.workspace_id,
        job_id=job_id,
        status=target_state,
        approval_state=payload.approval_state,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    repository.append_audit(
        workspace_id=payload.workspace_id,
        job_id=job_id,
        action=action_name,
        metadata={
            "from_status": job.status.value,
            "to_status": updated.status.value,
            "approval_state": updated.approval_state.value,
        },
    )
    return updated


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

    @app.post(
        "/v1/jobs/{job_id}/pause",
        dependencies=[Depends(require_api_token)],
        response_model=Job,
    )
    def pause_job(
        job_id: str,
        payload: JobStateTransitionRequest,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> Job:
        return _transition_job_state(
            repository=repository,
            job_id=job_id,
            payload=payload,
            target_state=JobStatus.PAUSED,
            action_name="job.pause",
        )

    @app.post(
        "/v1/jobs/{job_id}/resume",
        dependencies=[Depends(require_api_token)],
        response_model=Job,
    )
    def resume_job(
        job_id: str,
        payload: JobStateTransitionRequest,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> Job:
        effective_payload = payload
        if payload.approval_state is None:
            effective_payload = JobStateTransitionRequest(
                workspace_id=payload.workspace_id,
                approval_state=ApprovalState.APPROVED,
            )
        return _transition_job_state(
            repository=repository,
            job_id=job_id,
            payload=effective_payload,
            target_state=JobStatus.ACTIVE,
            action_name="job.resume",
        )

    @app.post(
        "/v1/jobs/{job_id}/archive",
        dependencies=[Depends(require_api_token)],
        response_model=Job,
    )
    def archive_job(
        job_id: str,
        payload: JobStateTransitionRequest,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> Job:
        return _transition_job_state(
            repository=repository,
            job_id=job_id,
            payload=payload,
            target_state=JobStatus.ARCHIVED,
            action_name="job.archive",
        )

    @app.get(
        "/v1/jobs/{job_id}/audit",
        dependencies=[Depends(require_api_token)],
        response_model=list[AuditRecord],
    )
    def list_job_audit(
        job_id: str,
        workspace_id: str,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> list[AuditRecord]:
        job = repository.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        if workspace_id != job.workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workspace_id does not match the job workspace.",
            )
        return repository.list_audit(workspace_id=workspace_id, job_id=job_id)

    @app.post(
        "/v1/jobs/{job_id}/arms:batch_register",
        dependencies=[Depends(require_api_token)],
        response_model=ArmBulkRegisterResponse,
    )
    def batch_register_arms(
        job_id: str,
        payload: ArmBulkRegisterRequest,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> ArmBulkRegisterResponse:
        job = repository.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        if payload.workspace_id != job.workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workspace_id does not match the job workspace.",
            )

        registered: list[Arm] = []
        for arm_input in payload.arms:
            arm = Arm(
                workspace_id=payload.workspace_id,
                job_id=job_id,
                arm_id=arm_input.arm_id,
                name=arm_input.name,
                arm_type=arm_input.arm_type,
                payload_ref=arm_input.payload_ref,
                metadata=arm_input.metadata,
            )
            registered.append(repository.upsert_arm(arm))

        repository.append_audit(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            action="arm.batch_register",
            metadata={"registered_count": len(registered)},
        )

        return ArmBulkRegisterResponse(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            registered_count=len(registered),
            arms=repository.list_arms(workspace_id=payload.workspace_id, job_id=job_id),
        )

    @app.get(
        "/v1/jobs/{job_id}/arms",
        dependencies=[Depends(require_api_token)],
        response_model=list[Arm],
    )
    def list_job_arms(
        job_id: str,
        workspace_id: str,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> list[Arm]:
        job = repository.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        if workspace_id != job.workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workspace_id does not match the job workspace.",
            )
        return repository.list_arms(workspace_id=workspace_id, job_id=job_id)

    @app.post(
        "/v1/jobs/{job_id}/arms/{arm_id}:lifecycle",
        dependencies=[Depends(require_api_token)],
        response_model=Arm,
    )
    def update_arm_lifecycle(
        job_id: str,
        arm_id: str,
        payload: ArmLifecycleRequest,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> Arm:
        job = repository.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        if payload.workspace_id != job.workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workspace_id does not match the job workspace.",
            )

        target_state = {
            ArmLifecycleAction.HOLD: ArmState.HELD_OUT,
            ArmLifecycleAction.RETIRE: ArmState.RETIRED,
            ArmLifecycleAction.RESUME: ArmState.ACTIVE,
        }[payload.action]

        updated = repository.set_arm_state(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            arm_id=arm_id,
            state=target_state,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Arm '{arm_id}' not found for job '{job_id}'.",
            )

        repository.append_audit(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            action=f"arm.{payload.action.value}",
            metadata={"arm_id": arm_id, "state": updated.state.value},
        )
        return updated

    return app


app = create_app()
