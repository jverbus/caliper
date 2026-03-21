from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    surface_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    approval_state: Mapped[str] = mapped_column(String(32), default="not_required")
    objective_spec: Mapped[dict[str, object]] = mapped_column(JSON)
    guardrail_spec: Mapped[dict[str, object]] = mapped_column(JSON)
    policy_spec: Mapped[dict[str, object]] = mapped_column(JSON)
    segment_spec: Mapped[dict[str, object]] = mapped_column(JSON)
    schedule_spec: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArmRow(Base):
    __tablename__ = "arms"

    arm_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    arm_type: Mapped[str] = mapped_column(String(64))
    payload_ref: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DecisionRow(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    unit_id: Mapped[str] = mapped_column(String(255), index=True)
    arm_id: Mapped[str] = mapped_column(String(64), index=True)
    propensity: Mapped[float] = mapped_column(Float)
    policy_family: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64))
    context_schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diagnostics_json: Mapped[dict[str, object]] = mapped_column(JSON)
    candidate_arms_json: Mapped[list[str]] = mapped_column(JSON)
    context_json: Mapped[dict[str, object]] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"

    idempotency_record_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    endpoint: Mapped[str] = mapped_column(String(128), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        Index(
            "idx_idempotency_scope_key",
            "workspace_id",
            "endpoint",
            "idempotency_key",
            unique=True,
        ),
    )


class ExposureRow(Base):
    __tablename__ = "exposures"

    exposure_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    decision_id: Mapped[str] = mapped_column(String(64), index=True)
    unit_id: Mapped[str] = mapped_column(String(255), index=True)
    exposure_type: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON)


class OutcomeRow(Base):
    __tablename__ = "outcomes"

    outcome_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    decision_id: Mapped[str] = mapped_column(String(64), index=True)
    unit_id: Mapped[str] = mapped_column(String(255), index=True)
    events_json: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    attribution_window_json: Mapped[dict[str, object]] = mapped_column(JSON)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON)


class GuardrailEventRow(Base):
    __tablename__ = "guardrail_events"

    guardrail_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(64))
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON)


class PolicySnapshotRow(Base):
    __tablename__ = "policy_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    policy_family: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditRow(Base):
    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON)


class EventRow(Base):
    __tablename__ = "event_ledger"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)

    __table_args__ = (
        Index(
            "idx_event_ledger_scope_idempotency",
            "workspace_id",
            "job_id",
            "event_type",
            "idempotency_key",
        ),
    )


class ProjectionMetricRow(Base):
    __tablename__ = "projection_metrics"

    projection_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    arm_id: Mapped[str] = mapped_column(String(64), index=True)
    assignments: Mapped[int] = mapped_column(Integer, default=0)
    exposures: Mapped[int] = mapped_column(Integer, default=0)
    outcomes: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index(
            "idx_projection_metrics_unique",
            "workspace_id",
            "job_id",
            "arm_id",
            unique=True,
        ),
    )


class ProjectionRebuildAuditRow(Base):
    __tablename__ = "projection_rebuild_audit"

    rebuild_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    rebuilt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_count: Mapped[int] = mapped_column(Integer)
    start_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportRunRow(Base):
    __tablename__ = "report_runs"

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)


class ScheduledTaskRow(Base):
    __tablename__ = "scheduled_tasks"

    task_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "idx_scheduled_task_scope_status_due",
            "workspace_id",
            "job_id",
            "status",
            "due_at",
        ),
    )


class AutotuneCandidateRow(Base):
    __tablename__ = "autotune_candidates"

    candidate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(128), index=True)
    candidate_type: Mapped[str] = mapped_column(String(64))
    parent_candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    editable_surface: Mapped[str] = mapped_column(String(255))
    content_json: Mapped[dict[str, object]] = mapped_column(JSON)
    complexity_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AutotuneRunRow(Base):
    __tablename__ = "autotune_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(128), index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    baseline_candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    simulation_config_snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)
    seed: Mapped[int] = mapped_column(Integer)
    budget: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    evaluator_version: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AutotuneResultRow(Base):
    __tablename__ = "autotune_results"

    result_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)
    score_breakdown_json: Mapped[dict[str, object]] = mapped_column(JSON)
    decision_summary_snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)
    analytics_snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)
    keep_discard: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hard_fail_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AutotunePromotionRow(Base):
    __tablename__ = "autotune_promotions"

    promotion_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    promoted_by: Mapped[str] = mapped_column(String(128))
    target_surface: Mapped[str] = mapped_column(String(255))
    confirmation: Mapped[str] = mapped_column(String(255))
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
