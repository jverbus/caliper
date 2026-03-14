from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from caliper_adapters import WorkflowAdapter
from caliper_core.models import (
    AssignResult,
    DecisionDiagnostics,
    OutcomeCreate,
    OutcomeEvent,
    PolicyFamily,
)


class _FakeWorkflowClient:
    def __init__(self) -> None:
        self.assign_payloads: list[Any] = []
        self.exposures: list[Any] = []
        self.outcomes: list[OutcomeCreate] = []

    def assign(self, payload: Any) -> AssignResult:
        self.assign_payloads.append(payload)
        return AssignResult(
            workspace_id=payload.workspace_id,
            job_id=payload.job_id,
            unit_id=payload.unit_id,
            arm_id="workflow-arm-a",
            propensity=0.75,
            policy_family=PolicyFamily.THOMPSON_SAMPLING,
            policy_version="snapshot-3",
            diagnostics=DecisionDiagnostics(
                scores={"workflow-arm-a": 0.75},
                reason="thompson_sampling",
                fallback_used=False,
            ),
            candidate_arms=["workflow-arm-a"],
            context=payload.context,
        )

    def log_exposure(self, payload: Any) -> Any:
        self.exposures.append(payload)
        return payload

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate:
        self.outcomes.append(payload)
        return payload


def test_workflow_assignment_logs_executed_exposure() -> None:
    client = _FakeWorkflowClient()
    adapter = WorkflowAdapter(client=client, workspace_id="ws-flow", job_id="job-flow")

    assignment = adapter.assign_workflow(
        unit_id="run-001",
        idempotency_key="assign-run-001",
        candidate_arms=["workflow-arm-a"],
        context={"workflow": "nurture", "step": 2},
    )

    assert assignment.arm_id == "workflow-arm-a"
    assert assignment.propensity == 0.75
    assert len(client.assign_payloads) == 1
    assert len(client.exposures) == 1
    assert client.exposures[0].exposure_type.value == "executed"
    assert client.exposures[0].metadata["surface"] == "workflow"


def test_workflow_execution_logs_objective_latency_and_cost() -> None:
    client = _FakeWorkflowClient()
    adapter = WorkflowAdapter(
        client=client,
        workspace_id="ws-flow",
        job_id="job-flow",
        latency_metric="latency_ms",
        cost_metric="llm_cost_usd",
    )

    outcome = adapter.log_execution_outcome(
        unit_id="run-001",
        decision_id="dec-001",
        objective_value=1.0,
        latency_ms=872.0,
        cost_usd=0.034,
        metadata={"model": "gpt-5.3-codex"},
    )

    assert outcome.metadata["source"] == "workflow"
    assert outcome.metadata["model"] == "gpt-5.3-codex"
    assert [event.outcome_type for event in outcome.events] == [
        "objective",
        "latency_ms",
        "llm_cost_usd",
    ]
    assert [event.value for event in outcome.events] == [1.0, 872.0, 0.034]


def test_workflow_human_acceptance_outcome() -> None:
    client = _FakeWorkflowClient()
    adapter = WorkflowAdapter(client=client, workspace_id="ws-flow", job_id="job-flow")
    reviewed_at = datetime(2026, 3, 14, 19, 45, tzinfo=UTC)

    outcome = adapter.log_human_acceptance(
        unit_id="run-001",
        decision_id="dec-001",
        accepted=True,
        reviewed_at=reviewed_at,
        reviewer="ops@caliper",
    )

    assert len(outcome.events) == 1
    event: OutcomeEvent = outcome.events[0]
    assert event.outcome_type == "human_acceptance"
    assert event.value == 1.0
    assert event.timestamp == reviewed_at
    assert outcome.metadata["reviewer"] == "ops@caliper"
    assert outcome.metadata["reviewed_at"] == reviewed_at.isoformat()
