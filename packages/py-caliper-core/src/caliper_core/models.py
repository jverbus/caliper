from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class JobStatus(StrEnum):
    DRAFT = "draft"
    SHADOW = "shadow"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ApprovalState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SurfaceType(StrEnum):
    WORKFLOW = "workflow"
    WEB = "web"
    EMAIL = "email"
    ORG_ROUTER = "org_router"


class ArmType(StrEnum):
    ARTIFACT = "artifact"
    WORKFLOW = "workflow"
    ORGANIZATION = "organization"


class ArmState(StrEnum):
    ACTIVE = "active"
    HELD_OUT = "held_out"
    RETIRED = "retired"


class ArmLifecycleAction(StrEnum):
    HOLD = "hold"
    RETIRE = "retire"
    RESUME = "resume"


class PolicyFamily(StrEnum):
    FIXED_SPLIT = "fixed_split"
    EPSILON_GREEDY = "epsilon_greedy"
    UCB1 = "ucb1"
    THOMPSON_SAMPLING = "thompson_sampling"
    DISJOINT_LINUCB = "disjoint_linucb"
    VW_CB_ADF = "vw_cb_adf"


class GuardrailAction(StrEnum):
    ANNOTATE = "annotate"
    CAP = "cap"
    DEMOTE = "demote"
    PAUSE = "pause"
    REQUIRE_MANUAL_RESUME = "require_manual_resume"


class ExposureType(StrEnum):
    RENDERED = "rendered"
    EXECUTED = "executed"


class ObjectiveSpec(BaseModel):
    reward_formula: str
    penalties: list[str] = Field(default_factory=list)
    secondary_metrics: list[str] = Field(default_factory=list)


class GuardrailRule(BaseModel):
    metric: str
    op: str
    threshold: float
    action: GuardrailAction


class GuardrailSpec(BaseModel):
    rules: list[GuardrailRule] = Field(default_factory=list)


class UpdateCadence(BaseModel):
    mode: str = "periodic"
    seconds: int | None = None


class PolicySpec(BaseModel):
    policy_family: PolicyFamily
    params: dict[str, Any] = Field(default_factory=dict)
    update_cadence: UpdateCadence = Field(default_factory=UpdateCadence)
    context_schema_version: str | None = None


class SegmentSpec(BaseModel):
    dimensions: list[str] = Field(default_factory=list)


class ScheduleSpec(BaseModel):
    report_cron: str | None = None


class JobCreate(BaseModel):
    workspace_id: str
    name: str
    surface_type: SurfaceType
    objective_spec: ObjectiveSpec
    guardrail_spec: GuardrailSpec
    policy_spec: PolicySpec
    segment_spec: SegmentSpec = Field(default_factory=SegmentSpec)
    schedule_spec: ScheduleSpec = Field(default_factory=ScheduleSpec)


class Job(JobCreate):
    job_id: str = Field(default_factory=lambda: new_id("job"))
    status: JobStatus = JobStatus.DRAFT
    approval_state: ApprovalState = ApprovalState.NOT_REQUIRED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class JobPatch(BaseModel):
    name: str | None = None
    objective_spec: ObjectiveSpec | None = None
    guardrail_spec: GuardrailSpec | None = None
    policy_spec: PolicySpec | None = None
    segment_spec: SegmentSpec | None = None
    schedule_spec: ScheduleSpec | None = None


class JobStateTransitionRequest(BaseModel):
    workspace_id: str
    approval_state: ApprovalState | None = None


class AuditRecord(BaseModel):
    action: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime


class ArmInput(BaseModel):
    arm_id: str
    name: str
    arm_type: ArmType
    payload_ref: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Arm(ArmInput):
    workspace_id: str
    job_id: str
    state: ArmState = ArmState.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ArmBulkRegisterRequest(BaseModel):
    workspace_id: str
    arms: list[ArmInput] = Field(default_factory=list)


class ArmBulkRegisterResponse(BaseModel):
    workspace_id: str
    job_id: str
    registered_count: int
    arms: list[Arm]


class ArmLifecycleRequest(BaseModel):
    workspace_id: str
    action: ArmLifecycleAction


class DecisionDiagnostics(BaseModel):
    scores: dict[str, float] = Field(default_factory=dict)
    reason: str = ""
    fallback_used: bool = False


class AssignRequest(BaseModel):
    workspace_id: str
    job_id: str
    unit_id: str
    candidate_arms: list[str] | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


class AssignResult(BaseModel):
    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    workspace_id: str
    job_id: str
    unit_id: str
    arm_id: str
    propensity: float = Field(gt=0, le=1)
    policy_family: PolicyFamily
    policy_version: str
    context_schema_version: str | None = None
    diagnostics: DecisionDiagnostics = Field(default_factory=DecisionDiagnostics)
    candidate_arms: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class ShadowAssignRequest(AssignRequest):
    shadow_snapshot_id: str


class ShadowAssignResult(BaseModel):
    live_decision: AssignResult
    shadow_decision: AssignResult


class ExposureCreate(BaseModel):
    workspace_id: str
    job_id: str
    decision_id: str
    unit_id: str
    exposure_type: ExposureType = ExposureType.RENDERED
    timestamp: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutcomeEvent(BaseModel):
    outcome_type: str
    value: float
    metric_kind: str = "value"
    denominator: float | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class AttributionWindow(BaseModel):
    hours: int = 24


class OutcomeCreate(BaseModel):
    workspace_id: str
    job_id: str
    decision_id: str
    unit_id: str
    events: list[OutcomeEvent]
    attribution_window: AttributionWindow = Field(default_factory=AttributionWindow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailEvent(BaseModel):
    guardrail_event_id: str = Field(default_factory=lambda: new_id("gr"))
    workspace_id: str
    job_id: str
    metric: str
    status: str
    action: GuardrailAction | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicySnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: new_id("ps"))
    workspace_id: str
    job_id: str
    policy_family: PolicyFamily
    policy_version: str
    payload: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    activated_at: datetime | None = None


class PolicySnapshotCreateRequest(BaseModel):
    workspace_id: str
    policy_family: PolicyFamily
    policy_version: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PolicySnapshotActivateRequest(BaseModel):
    workspace_id: str


class PolicySnapshotRollbackRequest(BaseModel):
    workspace_id: str
    target_snapshot_id: str | None = None


class ReportGenerateRequest(BaseModel):
    workspace_id: str


class ReportSummary(BaseModel):
    arm_id: str
    assignments: int = 0
    exposures: int = 0
    outcomes: int = 0
    avg_reward: float = 0.0
    assignment_share: float = 0.0


class SegmentFinding(BaseModel):
    segment: str
    leader_arm_id: str | None = None
    observations: int = 0


class Recommendation(BaseModel):
    title: str
    detail: str


class ReportPayload(BaseModel):
    report_id: str = Field(default_factory=lambda: new_id("rpt"))
    workspace_id: str
    job_id: str
    generated_at: datetime = Field(default_factory=utc_now)
    leaders: list[ReportSummary] = Field(default_factory=list)
    traffic_shifts: list[str] = Field(default_factory=list)
    guardrails: list[dict[str, Any]] = Field(default_factory=list)
    segment_findings: list[SegmentFinding] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    markdown: str
    html: str
