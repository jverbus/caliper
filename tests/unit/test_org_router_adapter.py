from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from caliper_adapters import OrgRouterAdapter
from caliper_core.models import (
    AssignResult,
    DecisionDiagnostics,
    ExposureCreate,
    OutcomeCreate,
    OutcomeEvent,
    PolicyFamily,
)


class _FakeOrgRouterClient:
    def __init__(self) -> None:
        self.assign_payloads: list[Any] = []
        self.exposures: list[ExposureCreate] = []
        self.outcomes: list[OutcomeCreate] = []

    def assign(self, payload: Any) -> AssignResult:
        self.assign_payloads.append(payload)
        return AssignResult(
            workspace_id=payload.workspace_id,
            job_id=payload.job_id,
            unit_id=payload.unit_id,
            arm_id="org-cluster-b",
            propensity=0.64,
            policy_family=PolicyFamily.DISJOINT_LINUCB,
            policy_version="snapshot-org-2",
            diagnostics=DecisionDiagnostics(
                scores={"org-cluster-a": 0.41, "org-cluster-b": 0.64},
                reason="disjoint_linucb",
                fallback_used=False,
            ),
            candidate_arms=payload.candidate_arms or [],
            context=payload.context,
        )

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate:
        self.exposures.append(payload)
        return payload

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate:
        self.outcomes.append(payload)
        return payload


def test_route_task_assigns_organization_and_logs_executed_exposure() -> None:
    client = _FakeOrgRouterClient()
    adapter = OrgRouterAdapter(
        client=client,
        workspace_id="ws-org",
        job_id="job-org",
        child_policy_refs={"org-cluster-b": "policy/workflow-router-v2"},
    )

    route = adapter.route_task(
        unit_id="task-001",
        idempotency_key="org-route-001",
        candidate_arms=["org-cluster-a", "org-cluster-b"],
        context={"task_type": "triage", "priority": "high"},
    )

    assert route.arm_id == "org-cluster-b"
    assert route.propensity == 0.64
    assert route.child_policy_ref == "policy/workflow-router-v2"
    assert client.assign_payloads[0].context["surface"] == "org_router"
    assert len(client.exposures) == 1
    exposure = client.exposures[0]
    assert exposure.exposure_type.value == "executed"
    assert exposure.metadata["surface"] == "org_router"
    assert exposure.metadata["organization_arm_id"] == "org-cluster-b"


def test_log_task_completion_includes_objective_speed_cost_and_downstream_events() -> None:
    client = _FakeOrgRouterClient()
    adapter = OrgRouterAdapter(
        client=client,
        workspace_id="ws-org",
        job_id="job-org",
        latency_metric="completion_ms",
        cost_metric="llm_cost_usd",
    )

    outcome = adapter.log_task_completion(
        unit_id="task-002",
        decision_id="dec-org-002",
        objective_value=0.92,
        latency_ms=1280.0,
        cost_usd=0.083,
        metadata={"organization_arm_id": "org-cluster-b"},
        downstream_events=[
            OutcomeEvent(
                outcome_type="handoff_success",
                value=1.0,
                timestamp=datetime(2026, 3, 15, 0, 5, tzinfo=UTC),
            )
        ],
    )

    assert [event.outcome_type for event in outcome.events] == [
        "objective",
        "completion_ms",
        "llm_cost_usd",
        "handoff_success",
    ]
    assert [event.value for event in outcome.events] == [0.92, 1280.0, 0.083, 1.0]
    assert outcome.metadata["source"] == "org_router"
    assert outcome.metadata["organization_arm_id"] == "org-cluster-b"
    assert len(client.outcomes) == 1
