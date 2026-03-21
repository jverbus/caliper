from __future__ import annotations

from caliper_core.context import ContextValidationError, validate_and_redact_context
from caliper_core.events import EventEnvelope
from caliper_core.models import AssignRequest, AssignResult, Job, PolicySnapshot
from caliper_policies.engine import AssignmentEngine, AssignmentError
from caliper_storage import SQLRepository
from fastapi import HTTPException, status


def apply_active_policy_snapshot(*, job: Job, snapshot: PolicySnapshot) -> Job:
    policy_spec = job.policy_spec.model_copy(
        update={
            "policy_family": snapshot.policy_family,
            "params": {**snapshot.payload, "policy_version": snapshot.policy_version},
        }
    )
    return job.model_copy(update={"policy_spec": policy_spec})


def resolve_effective_job(
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
    return apply_active_policy_snapshot(job=job, snapshot=active_snapshot)


def evaluate_assignment(
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


def is_contextual_runtime_snapshot(snapshot: PolicySnapshot) -> bool:
    runtime = snapshot.payload.get("runtime")
    return runtime == "contextual" or bool(snapshot.payload.get("requires_contextual_gate"))


def contextual_gate_failures(
    *,
    repository: SQLRepository,
    snapshot: PolicySnapshot,
) -> list[str]:
    if not is_contextual_runtime_snapshot(snapshot):
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


def run_promotion_checks(
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
    effective_job = resolve_effective_job(
        repository=repository,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    shadow_job = apply_active_policy_snapshot(job=effective_job, snapshot=snapshot)

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
        shadow_decision = evaluate_assignment(
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


def emit_policy_updated_event(
    *,
    repository: SQLRepository,
    workspace_id: str,
    job_id: str,
    snapshot: PolicySnapshot,
    rollback: bool = False,
) -> None:
    repository.append(
        EventEnvelope(
            workspace_id=workspace_id,
            job_id=job_id,
            event_type="policy.updated",
            entity_id=snapshot.snapshot_id,
            payload={
                "snapshot_id": snapshot.snapshot_id,
                "policy_family": snapshot.policy_family.value,
                "policy_version": snapshot.policy_version,
                "activated_at": snapshot.activated_at.isoformat()
                if snapshot.activated_at
                else None,
                **({"rollback": True} if rollback else {}),
            },
        )
    )
