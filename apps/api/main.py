from __future__ import annotations

import hashlib
import json
from typing import Annotated

from api.dependencies import (
    get_engine,
    get_repository,
    health_check,
    readiness_check,
    require_api_token,
)
from caliper_core.events import EventEnvelope
from caliper_core.models import (
    ApprovalState,
    Arm,
    ArmBulkRegisterRequest,
    ArmBulkRegisterResponse,
    ArmLifecycleAction,
    ArmLifecycleRequest,
    ArmState,
    AssignRequest,
    AssignResult,
    AuditRecord,
    ExposureCreate,
    Job,
    JobCreate,
    JobCreateResponse,
    JobPatch,
    JobStateTransitionRequest,
    JobStatus,
    OutcomeCreate,
    PolicySnapshot,
    PolicySnapshotActivateRequest,
    PolicySnapshotCreateRequest,
    PolicySnapshotRollbackRequest,
    ReportGenerateRequest,
    ReportPayload,
)
from caliper_policies.engine import AssignmentEngine, AssignmentError
from caliper_reports import ReportGenerator
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


def _request_hash(payload: object) -> str:
    if hasattr(payload, "model_dump"):
        body = payload.model_dump(mode="json")
    else:
        body = payload
    encoded = json.dumps(body, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _assign_request_hash(payload: AssignRequest) -> str:
    return _request_hash(payload)




def _apply_active_policy_snapshot(*, job: Job, snapshot: PolicySnapshot) -> Job:
    policy_spec = job.policy_spec.model_copy(
        update={
            "policy_family": snapshot.policy_family,
            "params": {**snapshot.payload, "policy_version": snapshot.policy_version},
        }
    )
    return job.model_copy(update={"policy_spec": policy_spec})
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

    @app.get(
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

    @app.post(
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

        repository.append(
            EventEnvelope(
                workspace_id=payload.workspace_id,
                job_id=job_id,
                event_type="policy.updated",
                entity_id=activated.snapshot_id,
                payload={
                    "snapshot_id": activated.snapshot_id,
                    "policy_family": activated.policy_family.value,
                    "policy_version": activated.policy_version,
                    "activated_at": (
                        activated.activated_at.isoformat()
                        if activated.activated_at
                        else None
                    ),
                },
            )
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

    @app.post(
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

        repository.append(
            EventEnvelope(
                workspace_id=payload.workspace_id,
                job_id=job_id,
                event_type="policy.updated",
                entity_id=activated.snapshot_id,
                payload={
                    "snapshot_id": activated.snapshot_id,
                    "policy_family": activated.policy_family.value,
                    "policy_version": activated.policy_version,
                    "rollback": True,
                    "activated_at": (
                        activated.activated_at.isoformat()
                        if activated.activated_at
                        else None
                    ),
                },
            )
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
        "/v1/assign",
        dependencies=[Depends(require_api_token)],
        response_model=AssignResult,
    )
    def assign(
        payload: AssignRequest,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> AssignResult:
        endpoint = "/v1/assign"
        request_hash = _assign_request_hash(payload)
        cached = repository.get_idempotent_response(
            workspace_id=payload.workspace_id,
            endpoint=endpoint,
            idempotency_key=payload.idempotency_key,
        )
        if cached is not None:
            cached_hash, cached_response = cached
            if cached_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=("Idempotency key already used with a different request payload."),
                )
            return AssignResult.model_validate(cached_response)

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

        active_snapshot = repository.get_active_snapshot(payload.workspace_id, payload.job_id)
        effective_job = (
            _apply_active_policy_snapshot(job=job, snapshot=active_snapshot)
            if active_snapshot is not None
            else job
        )

        engine = AssignmentEngine()
        arms = repository.list_arms(workspace_id=payload.workspace_id, job_id=payload.job_id)
        try:
            decision = engine.assign(job=effective_job, request=payload, arms=arms)
        except AssignmentError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

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
            request_hash=request_hash,
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

    @app.post(
        "/v1/exposures",
        dependencies=[Depends(require_api_token)],
        response_model=ExposureCreate,
    )
    def create_exposure(
        payload: ExposureCreate,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> ExposureCreate:
        endpoint = "/v1/exposures"
        request_hash = _request_hash(payload)
        idempotency_key = request_hash

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
            request_hash=request_hash,
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

    @app.post(
        "/v1/outcomes",
        dependencies=[Depends(require_api_token)],
        response_model=OutcomeCreate,
    )
    def create_outcome(
        payload: OutcomeCreate,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> OutcomeCreate:
        endpoint = "/v1/outcomes"
        request_hash = _request_hash(payload)
        idempotency_key = request_hash

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
            request_hash=request_hash,
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

    @app.post(
        "/v1/jobs/{job_id}/reports:generate",
        dependencies=[Depends(require_api_token)],
        response_model=ReportPayload,
    )
    def generate_report(
        job_id: str,
        payload: ReportGenerateRequest,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> ReportPayload:
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

        generator = ReportGenerator()
        report = generator.generate(
            job=job,
            arms=repository.list_arms(workspace_id=payload.workspace_id, job_id=job_id),
            decisions=repository.list_decisions(workspace_id=payload.workspace_id, job_id=job_id),
            exposures=len(
                repository.list_exposures(workspace_id=payload.workspace_id, job_id=job_id)
            ),
            outcomes=repository.list_outcomes(workspace_id=payload.workspace_id, job_id=job_id),
            guardrails=repository.list_guardrail_events(
                workspace_id=payload.workspace_id,
                job_id=job_id,
            ),
        )
        repository.save_report(report)
        repository.append_audit(
            workspace_id=payload.workspace_id,
            job_id=job_id,
            action="report.generated",
            metadata={"report_id": report.report_id},
        )
        return report

    @app.get(
        "/v1/jobs/{job_id}/reports/latest",
        dependencies=[Depends(require_api_token)],
        response_model=ReportPayload,
    )
    def get_latest_report(
        job_id: str,
        workspace_id: str,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> ReportPayload:
        report = repository.get_latest_report(workspace_id=workspace_id, job_id=job_id)
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No reports found for job '{job_id}'.",
            )
        return report

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
