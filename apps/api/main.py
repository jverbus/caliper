from __future__ import annotations

import hashlib
import json
from typing import Annotated

from caliper_core.context import ContextValidationError, validate_and_redact_context
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
    ShadowAssignRequest,
    ShadowAssignResult,
)
from caliper_policies.engine import AssignmentEngine, AssignmentError
from caliper_reports import ReportGenerator
from caliper_storage import SQLRepository
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import Engine

from apps.api.decision_service import get_decision_summary
from apps.api.dependencies import (
    get_engine,
    get_repository,
    health_check,
    readiness_check,
    require_api_token,
)

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


def _is_contextual_runtime_snapshot(snapshot: PolicySnapshot) -> bool:
    runtime = snapshot.payload.get("runtime")
    return runtime == "contextual" or bool(snapshot.payload.get("requires_contextual_gate"))


def _contextual_gate_failures(
    *,
    repository: SQLRepository,
    snapshot: PolicySnapshot,
) -> list[str]:
    if not _is_contextual_runtime_snapshot(snapshot):
        return []

    failures: list[str] = []
    gate = snapshot.payload.get("contextual_gate")
    if not isinstance(gate, dict):
        return ["contextual_gate payload is required for contextual runtime snapshots"]

    required_true = (
        "shadow_mode_validated",
        "ope_backtest_validated",
        "manual_review_approved",
    )
    for key in required_true:
        if gate.get(key) is not True:
            failures.append(f"contextual_gate.{key} must be true")

    if gate.get("context_schema_version") in (None, ""):
        failures.append("contextual_gate.context_schema_version is required")

    audits = repository.list_audit(workspace_id=snapshot.workspace_id, job_id=snapshot.job_id)
    gate_checks = [
        record
        for record in audits
        if record.action == "policy.snapshot.promotion_checks.completed"
        and record.metadata.get("snapshot_id") == snapshot.snapshot_id
    ]
    if not gate_checks:
        failures.append(
            "promotion checks must be run for this snapshot before contextual activation"
        )
    else:
        latest_checks = gate_checks[-1]
        if latest_checks.metadata.get("shadow_diff_ready") is not True:
            failures.append("shadow-vs-live diff check did not pass")
        if latest_checks.metadata.get("replay_ready") is not True:
            failures.append("replay export check did not pass")
        if latest_checks.metadata.get("obp_ready") is not True:
            failures.append("OBP preparation check did not pass")

    return failures


def _run_promotion_checks(
    *,
    repository: SQLRepository,
    workspace_id: str,
    job_id: str,
    snapshot: PolicySnapshot,
) -> dict[str, object]:
    try:
        from caliper_ope import ReplayExporter, prepare_obp_data, summarize_dataset

        replay_records = ReplayExporter(repository).export(
            workspace_id=workspace_id,
            job_id=job_id,
        )
        replay_summary = summarize_dataset(replay_records)
        replay_ready = replay_summary.count > 0
        obp_runtime_available = True
    except ModuleNotFoundError:
        replay_records = []
        replay_summary = type("ReplaySummary", (), {"count": 0, "average_reward": 0.0})()
        replay_ready = False
        obp_runtime_available = False

    decisions = repository.list_decisions(workspace_id=workspace_id, job_id=job_id)
    effective_job = _resolve_effective_job(
        repository=repository,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    shadow_job = _apply_active_policy_snapshot(job=effective_job, snapshot=snapshot)

    compared_count = 0
    disagreement_count = 0
    for decision in decisions:
        candidate_arms = decision.candidate_arms if decision.candidate_arms else None
        payload = AssignRequest(
            workspace_id=workspace_id,
            job_id=job_id,
            unit_id=decision.unit_id,
            candidate_arms=candidate_arms,
            context=decision.context,
            idempotency_key=f"promotion-check-shadow-{snapshot.snapshot_id}-{decision.decision_id}",
        )
        shadow_decision = _evaluate_assignment(
            repository=repository,
            payload=payload,
            effective_job=shadow_job,
        )
        compared_count += 1
        if shadow_decision.arm_id != decision.arm_id:
            disagreement_count += 1

    shadow_diff_ready = compared_count > 0
    disagreement_rate = (
        float(disagreement_count) / float(compared_count) if compared_count > 0 else None
    )

    obp_ready = False
    obp_error: str | None = None
    if not obp_runtime_available:
        obp_error = "caliper_ope package is not available in this runtime"
    elif replay_records:
        try:
            prepare_obp_data(replay_records)
            obp_ready = True
        except Exception as exc:
            obp_error = str(exc)

    checks = {
        "snapshot_id": snapshot.snapshot_id,
        "replay_ready": replay_ready,
        "replay_count": replay_summary.count,
        "replay_average_reward": replay_summary.average_reward,
        "shadow_diff_ready": shadow_diff_ready,
        "shadow_compared_count": compared_count,
        "shadow_disagreement_count": disagreement_count,
        "shadow_disagreement_rate": disagreement_rate,
        "obp_ready": obp_ready,
        "obp_error": obp_error,
    }
    repository.append_audit(
        workspace_id=workspace_id,
        job_id=job_id,
        action="policy.snapshot.promotion_checks.completed",
        metadata=checks,
    )
    return checks


def _resolve_effective_job(
    *,
    repository: SQLRepository,
    workspace_id: str,
    job_id: str,
) -> Job:
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

    active_snapshot = repository.get_active_snapshot(workspace_id, job_id)
    if active_snapshot is None:
        return job
    return _apply_active_policy_snapshot(job=job, snapshot=active_snapshot)


def _evaluate_assignment(
    *,
    repository: SQLRepository,
    payload: AssignRequest,
    effective_job: Job,
) -> AssignResult:
    try:
        context_result = validate_and_redact_context(
            context=payload.context,
            policy_spec=effective_job.policy_spec,
        )
    except ContextValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    sanitized_payload = payload.model_copy(update={"context": context_result.sanitized_context})

    engine = AssignmentEngine()
    arms = repository.list_arms(workspace_id=payload.workspace_id, job_id=payload.job_id)
    try:
        return engine.assign(job=effective_job, request=sanitized_payload, arms=arms)
    except AssignmentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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

    @app.get("/decision/summary")
    def decision_summary(guardrail_regression: bool | None = None) -> dict[str, str]:
        summary = get_decision_summary(guardrail_regression=guardrail_regression)
        return summary.model_dump(mode="json")

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

    @app.get("/v1/jobs", dependencies=[Depends(require_api_token)], response_model=list[Job])
    def list_jobs(
        repository: Annotated[SQLRepository, Depends(get_repository)],
        workspace_id: str | None = None,
    ) -> list[Job]:
        return repository.list_jobs(workspace_id=workspace_id)

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

    @app.get(
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

        failures = _contextual_gate_failures(repository=repository, snapshot=snapshot)
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
            "is_contextual_runtime": _is_contextual_runtime_snapshot(snapshot),
            "passed": passed,
            "failures": failures,
        }

    @app.post(
        "/v1/jobs/{job_id}/policy-snapshots/{snapshot_id}:run-promotion-checks",
        dependencies=[Depends(require_api_token)],
    )
    def run_promotion_checks(
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

        return _run_promotion_checks(
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

        failures = _contextual_gate_failures(repository=repository, snapshot=snapshot)
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

        if _is_contextual_runtime_snapshot(snapshot):
            repository.append_audit(
                workspace_id=payload.workspace_id,
                job_id=job_id,
                action="policy.snapshot.contextual_gate.passed",
                metadata={
                    "snapshot_id": snapshot_id,
                },
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
                        activated.activated_at.isoformat() if activated.activated_at else None
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

    @app.post(
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
                        activated.activated_at.isoformat() if activated.activated_at else None
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

        effective_job = _resolve_effective_job(
            repository=repository,
            workspace_id=payload.workspace_id,
            job_id=payload.job_id,
        )
        decision = _evaluate_assignment(
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
        "/v1/assign:shadow",
        dependencies=[Depends(require_api_token)],
        response_model=ShadowAssignResult,
    )
    def assign_shadow(
        payload: ShadowAssignRequest,
        repository: Annotated[SQLRepository, Depends(get_repository)],
    ) -> ShadowAssignResult:
        effective_job = _resolve_effective_job(
            repository=repository,
            workspace_id=payload.workspace_id,
            job_id=payload.job_id,
        )
        live_decision = _evaluate_assignment(
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

        shadow_job = _apply_active_policy_snapshot(job=effective_job, snapshot=snapshot)
        shadow_decision = _evaluate_assignment(
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
            exposures=repository.list_exposures(workspace_id=payload.workspace_id, job_id=job_id),
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
