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
from caliper_storage import SQLRepository
from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.dependencies import get_repository, require_api_token
from apps.api.services.common import assign_request_hash, request_hash
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
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> ExposureCreate:
    endpoint = "/v1/exposures"
    req_hash = request_hash(payload)
    idempotency_key = req_hash

    cached = repository.get_idempotent_response(
        workspace_id=payload.workspace_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
    )
    if cached is not None:
        _, cached_response = cached
        return ExposureCreate.model_validate(cached_response)

    job = repository.get_job(payload.job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{payload.job_id}' not found.",
        )
    if payload.workspace_id != job.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workspace_id does not match the job workspace.",
        )

    decision = repository.get_decision(payload.decision_id)
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision '{payload.decision_id}' not found.",
        )
    if (
        decision.workspace_id != payload.workspace_id
        or decision.job_id != payload.job_id
        or decision.unit_id != payload.unit_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision context does not match workspace_id/job_id/unit_id.",
        )

    exposure = repository.create_exposure(payload)
    repository.append(
        EventEnvelope(
            workspace_id=exposure.workspace_id,
            job_id=exposure.job_id,
            event_type="decision.exposed",
            entity_id=exposure.decision_id,
            idempotency_key=idempotency_key,
            payload={
                "workspace_id": exposure.workspace_id,
                "job_id": exposure.job_id,
                "decision_id": exposure.decision_id,
                "unit_id": exposure.unit_id,
                "exposure_type": exposure.exposure_type.value,
                "timestamp": exposure.timestamp.isoformat(),
                "metadata": exposure.metadata,
            },
        )
    )
    repository.save_idempotent_response(
        workspace_id=exposure.workspace_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
        response=exposure.model_dump(mode="json"),
    )
    repository.append_audit(
        workspace_id=exposure.workspace_id,
        job_id=exposure.job_id,
        action="decision.exposed",
        metadata={
            "decision_id": exposure.decision_id,
            "exposure_type": exposure.exposure_type.value,
        },
    )
    return exposure


@router.post(
    "/v1/outcomes",
    dependencies=[Depends(require_api_token)],
    response_model=OutcomeCreate,
)
def create_outcome(
    payload: OutcomeCreate,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> OutcomeCreate:
    endpoint = "/v1/outcomes"
    req_hash = request_hash(payload)
    idempotency_key = req_hash

    cached = repository.get_idempotent_response(
        workspace_id=payload.workspace_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
    )
    if cached is not None:
        _, cached_response = cached
        return OutcomeCreate.model_validate(cached_response)

    job = repository.get_job(payload.job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{payload.job_id}' not found.",
        )
    if payload.workspace_id != job.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workspace_id does not match the job workspace.",
        )

    decision = repository.get_decision(payload.decision_id)
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision '{payload.decision_id}' not found.",
        )
    if (
        decision.workspace_id != payload.workspace_id
        or decision.job_id != payload.job_id
        or decision.unit_id != payload.unit_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision context does not match workspace_id/job_id/unit_id.",
        )

    outcome = repository.create_outcome(payload)
    repository.append(
        EventEnvelope(
            workspace_id=outcome.workspace_id,
            job_id=outcome.job_id,
            event_type="outcome.observed",
            entity_id=outcome.decision_id,
            idempotency_key=idempotency_key,
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
    repository.save_idempotent_response(
        workspace_id=outcome.workspace_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
        response=outcome.model_dump(mode="json"),
    )
    repository.append_audit(
        workspace_id=outcome.workspace_id,
        job_id=outcome.job_id,
        action="outcome.observed",
        metadata={
            "decision_id": outcome.decision_id,
            "event_count": len(outcome.events),
        },
    )
    return outcome
