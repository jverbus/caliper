from __future__ import annotations

from typing import Annotated

from caliper_core.events import EventEnvelope
from caliper_core.models import (
    AssignRequest,
    AssignResult,
    ExposureCreate,
    OutcomeCreate,
    ShadowAssignRequest,
    ShadowAssignResult,
)
from caliper_sdk import CaliperService
from caliper_storage import SQLRepository
from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.dependencies import get_caliper_service, get_repository, require_api_token
from apps.api.services.common import assign_request_hash
from apps.api.services.policy import (
    apply_active_policy_snapshot,
    evaluate_assignment,
    resolve_effective_job,
)

router = APIRouter()


@router.post(
    "/v1/assign",
    dependencies=[Depends(require_api_token)],
    response_model=AssignResult,
)
def assign(
    payload: AssignRequest,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> AssignResult:
    endpoint = "/v1/assign"
    req_hash = assign_request_hash(payload)
    cached = repository.get_idempotent_response(
        workspace_id=payload.workspace_id,
        endpoint=endpoint,
        idempotency_key=payload.idempotency_key,
    )
    if cached is not None:
        cached_hash, cached_response = cached
        if cached_hash != req_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Idempotency key already used with a different request payload."),
            )
        return AssignResult.model_validate(cached_response)

    effective_job = resolve_effective_job(
        repository=repository,
        workspace_id=payload.workspace_id,
        job_id=payload.job_id,
    )
    decision = evaluate_assignment(
        repository=repository,
        payload=payload,
        effective_job=effective_job,
    )

    repository.create_decision(decision)
    repository.append(
        EventEnvelope(
            workspace_id=decision.workspace_id,
            job_id=decision.job_id,
            event_type="decision.assigned",
            entity_id=decision.decision_id,
            idempotency_key=payload.idempotency_key,
            payload={
                "decision_id": decision.decision_id,
                "workspace_id": decision.workspace_id,
                "job_id": decision.job_id,
                "unit_id": decision.unit_id,
                "candidate_arms": decision.candidate_arms,
                "chosen_arm": decision.arm_id,
                "propensity": decision.propensity,
                "policy_family": decision.policy_family.value,
                "policy_version": decision.policy_version,
                "context_schema_version": decision.context_schema_version,
                "context": decision.context,
                "diagnostics": decision.diagnostics.model_dump(mode="json"),
                "timestamp": decision.timestamp.isoformat(),
            },
        )
    )
    repository.save_idempotent_response(
        workspace_id=payload.workspace_id,
        endpoint=endpoint,
        idempotency_key=payload.idempotency_key,
        request_hash=req_hash,
        response=decision.model_dump(mode="json"),
    )
    repository.append_audit(
        workspace_id=payload.workspace_id,
        job_id=payload.job_id,
        action="decision.assigned",
        metadata={
            "decision_id": decision.decision_id,
            "arm_id": decision.arm_id,
            "idempotency_key": payload.idempotency_key,
        },
    )
    return decision


@router.post(
    "/v1/assign:shadow",
    dependencies=[Depends(require_api_token)],
    response_model=ShadowAssignResult,
)
def assign_shadow(
    payload: ShadowAssignRequest,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> ShadowAssignResult:
    effective_job = resolve_effective_job(
        repository=repository,
        workspace_id=payload.workspace_id,
        job_id=payload.job_id,
    )
    live_decision = evaluate_assignment(
        repository=repository,
        payload=payload,
        effective_job=effective_job,
    )

    snapshot = repository.get_snapshot(
        workspace_id=payload.workspace_id,
        job_id=payload.job_id,
        snapshot_id=payload.shadow_snapshot_id,
    )
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Shadow snapshot '{payload.shadow_snapshot_id}' "
                f"not found for job '{payload.job_id}'."
            ),
        )

    shadow_job = apply_active_policy_snapshot(job=effective_job, snapshot=snapshot)
    shadow_decision = evaluate_assignment(
        repository=repository,
        payload=payload,
        effective_job=shadow_job,
    )

    repository.append_audit(
        workspace_id=payload.workspace_id,
        job_id=payload.job_id,
        action="decision.shadow_evaluated",
        metadata={
            "idempotency_key": payload.idempotency_key,
            "shadow_snapshot_id": snapshot.snapshot_id,
            "live_arm_id": live_decision.arm_id,
            "shadow_arm_id": shadow_decision.arm_id,
        },
    )

    return ShadowAssignResult(live_decision=live_decision, shadow_decision=shadow_decision)


@router.post(
    "/v1/exposures",
    dependencies=[Depends(require_api_token)],
    response_model=ExposureCreate,
)
def create_exposure(
    payload: ExposureCreate,
    service: Annotated[CaliperService, Depends(get_caliper_service)],
) -> ExposureCreate:
    try:
        return service.log_exposure(payload)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if "not found" in detail:
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post(
    "/v1/outcomes",
    dependencies=[Depends(require_api_token)],
    response_model=OutcomeCreate,
)
def create_outcome(
    payload: OutcomeCreate,
    service: Annotated[CaliperService, Depends(get_caliper_service)],
) -> OutcomeCreate:
    try:
        return service.log_outcome(payload)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if "not found" in detail:
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=detail) from exc
