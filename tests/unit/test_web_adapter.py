from __future__ import annotations

from typing import Any

from caliper_adapters import WebAdapter
from caliper_core.models import (
    AssignResult,
    DecisionDiagnostics,
    ExposureCreate,
    OutcomeCreate,
    PolicyFamily,
)


class _FakeWebClient:
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
            arm_id="variant-b",
            propensity=0.55,
            policy_family=PolicyFamily.UCB1,
            policy_version="snapshot-web-3",
            diagnostics=DecisionDiagnostics(
                scores={"variant-a": 0.44, "variant-b": 0.55},
                reason="ucb1",
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


def test_web_assignment_supports_candidate_subset() -> None:
    client = _FakeWebClient()
    adapter = WebAdapter(client=client, workspace_id="ws-web", job_id="job-web")

    assignment = adapter.assign_request(
        unit_id="visitor-001",
        idempotency_key="req-001",
        candidate_arms=["variant-a", "variant-b"],
        context={"path": "/pricing", "logged_in": False},
    )

    assert assignment.arm_id == "variant-b"
    assert assignment.propensity == 0.55
    assert client.assign_payloads[0].candidate_arms == ["variant-a", "variant-b"]


def test_web_render_logs_rendered_exposure() -> None:
    client = _FakeWebClient()
    adapter = WebAdapter(client=client, workspace_id="ws-web", job_id="job-web")

    exposure = adapter.log_render(
        unit_id="visitor-001",
        decision_id="dec-001",
        metadata={"route": "/pricing", "variant_slot": "hero"},
    )

    assert exposure.exposure_type.value == "rendered"
    assert exposure.metadata["surface"] == "web"
    assert exposure.metadata["route"] == "/pricing"
    assert len(client.exposures) == 1


def test_web_click_and_conversion_outcomes_are_distinct() -> None:
    client = _FakeWebClient()
    adapter = WebAdapter(
        client=client,
        workspace_id="ws-web",
        job_id="job-web",
        click_metric="cta_click",
        conversion_metric="signup_conversion",
    )

    click = adapter.log_click(
        unit_id="visitor-001",
        decision_id="dec-001",
        metadata={"element": "hero_cta"},
    )
    conversion = adapter.log_conversion(
        unit_id="visitor-001",
        decision_id="dec-001",
        value=1.0,
        metadata={"funnel_stage": "signup_complete"},
    )

    assert click.events[0].outcome_type == "cta_click"
    assert click.events[0].value == 1.0
    assert click.metadata["source"] == "web"
    assert click.metadata["element"] == "hero_cta"

    assert conversion.events[0].outcome_type == "signup_conversion"
    assert conversion.events[0].value == 1.0
    assert conversion.metadata["funnel_stage"] == "signup_complete"
    assert len(client.outcomes) == 2
