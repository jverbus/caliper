from __future__ import annotations

from typing import Annotated

from caliper_core.models import (
    Arm,
    ArmBulkRegisterRequest,
    ArmBulkRegisterResponse,
    ArmLifecycleAction,
    ArmLifecycleRequest,
    ArmState,
)
from caliper_storage import SQLRepository
from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.dependencies import get_repository, require_api_token

router = APIRouter()


@router.post(
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


@router.get(
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


@router.post(
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
