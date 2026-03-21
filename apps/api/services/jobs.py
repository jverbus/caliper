from __future__ import annotations

from caliper_core.models import Job, JobStateTransitionRequest, JobStatus
from caliper_storage import SQLRepository
from fastapi import HTTPException, status

JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.DRAFT: {JobStatus.SHADOW, JobStatus.ACTIVE, JobStatus.ARCHIVED},
    JobStatus.SHADOW: {JobStatus.ACTIVE, JobStatus.PAUSED, JobStatus.ARCHIVED},
    JobStatus.ACTIVE: {JobStatus.PAUSED, JobStatus.COMPLETED, JobStatus.ARCHIVED},
    JobStatus.PAUSED: {JobStatus.ACTIVE, JobStatus.COMPLETED, JobStatus.ARCHIVED},
    JobStatus.COMPLETED: {JobStatus.ARCHIVED},
    JobStatus.ARCHIVED: set(),
}


def transition_job_state(
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
    if target_state not in JOB_TRANSITIONS[job.status]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"Invalid job state transition: {job.status.value} -> {target_state.value}."),
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
