from __future__ import annotations

from typing import Annotated

from caliper_core.models import (
    ApprovalState,
    AuditRecord,
    Job,
    JobCreate,
    JobCreateResponse,
    JobPatch,
    JobStateTransitionRequest,
    JobStatus,
    PolicySnapshot,
    PolicySnapshotActivateRequest,
    PolicySnapshotCreateRequest,
    PolicySnapshotRollbackRequest,
)
from caliper_storage import SQLRepository
from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.dependencies import get_repository, require_api_token
from apps.api.services.jobs import transition_job_state
from apps.api.services.policy import (
    contextual_gate_failures,
    emit_policy_updated_event,
    is_contextual_runtime_snapshot,
    run_promotion_checks,
)

router = APIRouter()


@router.post(
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


@router.get("/v1/jobs", dependencies=[Depends(require_api_token)], response_model=list[Job])
def list_jobs(
    repository: Annotated[SQLRepository, Depends(get_repository)],
    workspace_id: str | None = None,
) -> list[Job]:
    return repository.list_jobs(workspace_id=workspace_id)


@router.get("/v1/jobs/{job_id}", dependencies=[Depends(require_api_token)], response_model=Job)
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


@router.patch("/v1/jobs/{job_id}", dependencies=[Depends(require_api_token)], response_model=Job)
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


@router.post(
    "/v1/jobs/{job_id}/pause",
    dependencies=[Depends(require_api_token)],
    response_model=Job,
)
def pause_job(
    job_id: str,
    payload: JobStateTransitionRequest,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> Job:
    return transition_job_state(
        repository=repository,
        job_id=job_id,
        payload=payload,
        target_state=JobStatus.PAUSED,
        action_name="job.pause",
    )


@router.post(
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
    return transition_job_state(
        repository=repository,
        job_id=job_id,
        payload=effective_payload,
        target_state=JobStatus.ACTIVE,
        action_name="job.resume",
    )


@router.post(
    "/v1/jobs/{job_id}/archive",
    dependencies=[Depends(require_api_token)],
    response_model=Job,
)
def archive_job(
    job_id: str,
    payload: JobStateTransitionRequest,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> Job:
    return transition_job_state(
        repository=repository,
        job_id=job_id,
        payload=payload,
        target_state=JobStatus.ARCHIVED,
        action_name="job.archive",
    )


@router.get(
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


@router.post(
    "/v1/jobs/{job_id}/policy-snapshots",
    dependencies=[Depends(require_api_token)],
    response_model=PolicySnapshot,
)
def create_policy_snapshot(
    job_id: str,
    payload: PolicySnapshotCreateRequest,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> PolicySnapshot:
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

    snapshot = repository.save_snapshot(
        PolicySnapshot(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            policy_family=payload.policy_family,
            policy_version=payload.policy_version,
            payload=payload.payload,
        )
    )
    repository.append_audit(
        workspace_id=payload.workspace_id,
        job_id=job_id,
        action="policy.snapshot.created",
        metadata={
            "snapshot_id": snapshot.snapshot_id,
            "policy_version": snapshot.policy_version,
        },
    )
    return snapshot


@router.get(
    "/v1/jobs/{job_id}/policy-snapshots",
    dependencies=[Depends(require_api_token)],
    response_model=list[PolicySnapshot],
)
def list_policy_snapshots(
    job_id: str,
    workspace_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> list[PolicySnapshot]:
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
    return repository.list_snapshots(workspace_id, job_id)


@router.get(
    "/v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/contextual-gate",
    dependencies=[Depends(require_api_token)],
)
def check_contextual_promotion_gate(
    job_id: str,
    snapshot_id: str,
    workspace_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> dict[str, object]:
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

    snapshots = repository.list_snapshots(workspace_id, job_id)
    snapshot = next((item for item in snapshots if item.snapshot_id == snapshot_id), None)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{snapshot_id}' not found for job '{job_id}'.",
        )

    failures = contextual_gate_failures(repository=repository, snapshot=snapshot)
    passed = len(failures) == 0
    repository.append_audit(
        workspace_id=workspace_id,
        job_id=job_id,
        action="policy.snapshot.contextual_gate.checked",
        metadata={
            "snapshot_id": snapshot_id,
            "passed": passed,
            "failures": failures,
        },
    )

    return {
        "snapshot_id": snapshot_id,
        "is_contextual_runtime": is_contextual_runtime_snapshot(snapshot),
        "passed": passed,
        "failures": failures,
    }


@router.post(
    "/v1/jobs/{job_id}/policy-snapshots/{snapshot_id}:run-promotion-checks",
    dependencies=[Depends(require_api_token)],
)
def run_snapshot_promotion_checks(
    job_id: str,
    snapshot_id: str,
    workspace_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> dict[str, object]:
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

    snapshot = repository.get_snapshot(
        workspace_id=workspace_id,
        job_id=job_id,
        snapshot_id=snapshot_id,
    )
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{snapshot_id}' not found for job '{job_id}'.",
        )

    return run_promotion_checks(
        repository=repository,
        workspace_id=workspace_id,
        job_id=job_id,
        snapshot=snapshot,
    )


def _activate_policy_snapshot(
    *,
    job_id: str,
    snapshot_id: str,
    payload: PolicySnapshotActivateRequest,
    repository: SQLRepository,
) -> PolicySnapshot:
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

    snapshots = repository.list_snapshots(payload.workspace_id, job_id)
    snapshot = next((item for item in snapshots if item.snapshot_id == snapshot_id), None)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{snapshot_id}' not found for job '{job_id}'.",
        )

    failures = contextual_gate_failures(repository=repository, snapshot=snapshot)
    if failures:
        repository.append_audit(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            action="policy.snapshot.contextual_gate.blocked",
            metadata={
                "snapshot_id": snapshot_id,
                "failures": failures,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Contextual promotion gate checks failed.",
                "failures": failures,
            },
        )

    activated = repository.activate_snapshot(
        workspace_id=payload.workspace_id,
        job_id=job_id,
        snapshot_id=snapshot_id,
    )
    if activated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{snapshot_id}' not found for job '{job_id}'.",
        )

    if is_contextual_runtime_snapshot(snapshot):
        repository.append_audit(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            action="policy.snapshot.contextual_gate.passed",
            metadata={
                "snapshot_id": snapshot_id,
            },
        )

    emit_policy_updated_event(
        repository=repository,
        workspace_id=payload.workspace_id,
        job_id=job_id,
        snapshot=activated,
    )
    repository.append_audit(
        workspace_id=payload.workspace_id,
        job_id=job_id,
        action="policy.snapshot.activated",
        metadata={
            "snapshot_id": activated.snapshot_id,
            "policy_version": activated.policy_version,
        },
    )
    return activated


@router.post(
    "/v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/activate",
    dependencies=[Depends(require_api_token)],
    response_model=PolicySnapshot,
)
def activate_policy_snapshot(
    job_id: str,
    snapshot_id: str,
    payload: PolicySnapshotActivateRequest,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> PolicySnapshot:
    return _activate_policy_snapshot(
        job_id=job_id,
        snapshot_id=snapshot_id,
        payload=payload,
        repository=repository,
    )


@router.post(
    "/v1/jobs/{job_id}/policy-snapshots/{snapshot_id}/promote",
    dependencies=[Depends(require_api_token)],
    response_model=PolicySnapshot,
)
def promote_policy_snapshot(
    job_id: str,
    snapshot_id: str,
    payload: PolicySnapshotActivateRequest,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> PolicySnapshot:
    return _activate_policy_snapshot(
        job_id=job_id,
        snapshot_id=snapshot_id,
        payload=payload,
        repository=repository,
    )


@router.post(
    "/v1/jobs/{job_id}/policy-snapshots/rollback",
    dependencies=[Depends(require_api_token)],
    response_model=PolicySnapshot,
)
def rollback_policy_snapshot(
    job_id: str,
    payload: PolicySnapshotRollbackRequest,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> PolicySnapshot:
    snapshots = repository.list_snapshots(payload.workspace_id, job_id)
    if not snapshots:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No policy snapshots found for job '{job_id}'.",
        )

    active = next((snapshot for snapshot in snapshots if snapshot.is_active), None)
    if payload.target_snapshot_id is not None:
        target = next(
            (s for s in snapshots if s.snapshot_id == payload.target_snapshot_id),
            None,
        )
    else:
        target = None
        for snapshot in snapshots:
            if active is None or snapshot.snapshot_id != active.snapshot_id:
                target = snapshot
                break

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No prior snapshot available for rollback.",
        )

    activated = repository.activate_snapshot(
        workspace_id=payload.workspace_id,
        job_id=job_id,
        snapshot_id=target.snapshot_id,
    )
    if activated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{target.snapshot_id}' not found for job '{job_id}'.",
        )

    emit_policy_updated_event(
        repository=repository,
        workspace_id=payload.workspace_id,
        job_id=job_id,
        snapshot=activated,
        rollback=True,
    )
    repository.append_audit(
        workspace_id=payload.workspace_id,
        job_id=job_id,
        action="policy.snapshot.rollback",
        metadata={
            "snapshot_id": activated.snapshot_id,
            "policy_version": activated.policy_version,
        },
    )
    return activated
