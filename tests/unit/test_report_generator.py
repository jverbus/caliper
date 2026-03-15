from __future__ import annotations

from caliper_core.models import (
    Arm,
    ArmType,
    AssignResult,
    DecisionDiagnostics,
    ExposureCreate,
    GuardrailSpec,
    Job,
    ObjectiveSpec,
    OutcomeCreate,
    OutcomeEvent,
    PolicyFamily,
    PolicySpec,
    ScheduleSpec,
    SegmentSpec,
    SurfaceType,
)
from caliper_reports.generator import ReportGenerator


def _job() -> Job:
    return Job(
        workspace_id="ws-test",
        name="Report polish",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(
            reward_formula="signup",
            penalties=[],
            secondary_metrics=[],
        ),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.FIXED_SPLIT,
            params={"weights": {"arm-a": 1.0, "arm-b": 1.0}},
        ),
        segment_spec=SegmentSpec(dimensions=["country"]),
        schedule_spec=ScheduleSpec(report_cron=None),
    )


def _arms(job_id: str) -> list[Arm]:
    return [
        Arm(
            workspace_id="ws-test",
            job_id=job_id,
            arm_id="arm-a",
            name="Arm A",
            arm_type=ArmType.ARTIFACT,
            payload_ref="file://a",
            metadata={},
        ),
        Arm(
            workspace_id="ws-test",
            job_id=job_id,
            arm_id="arm-b",
            name="Arm B",
            arm_type=ArmType.ARTIFACT,
            payload_ref="file://b",
            metadata={},
        ),
    ]


def test_report_markdown_and_html_have_stable_sections() -> None:
    job = _job()
    decision = AssignResult(
        workspace_id="ws-test",
        job_id=job.job_id,
        unit_id="u1",
        arm_id="arm-a",
        propensity=1.0,
        policy_family=PolicyFamily.FIXED_SPLIT,
        policy_version="v1",
        diagnostics=DecisionDiagnostics(),
        context={"country": "US"},
    )
    report = ReportGenerator().generate(
        job=job,
        arms=_arms(job.job_id),
        decisions=[decision],
        exposures=[
            ExposureCreate(
                workspace_id="ws-test",
                job_id=job.job_id,
                decision_id=decision.decision_id,
                unit_id="u1",
            )
        ],
        outcomes=[],
        guardrails=[{"metric": "complaint_rate", "status": "breached", "action": "cap"}],
    )

    assert "## Summary" in report.markdown
    assert "| Arm | Avg reward | Assignment share | Assignments |" in report.markdown
    assert "Resolve guardrail alerts before scaling" in report.markdown
    assert report.html.startswith("<!doctype html><html>")
    assert "<table" in report.html
    assert "<h2>Recommendations</h2>" in report.html


def test_report_summary_uses_arm_scoped_exposure_and_outcome_counts() -> None:
    job = _job()
    decision_a = AssignResult(
        workspace_id="ws-test",
        job_id=job.job_id,
        unit_id="u1",
        arm_id="arm-a",
        propensity=1.0,
        policy_family=PolicyFamily.FIXED_SPLIT,
        policy_version="v1",
        diagnostics=DecisionDiagnostics(),
        context={"country": "US"},
    )
    decision_b = AssignResult(
        workspace_id="ws-test",
        job_id=job.job_id,
        unit_id="u2",
        arm_id="arm-b",
        propensity=1.0,
        policy_family=PolicyFamily.FIXED_SPLIT,
        policy_version="v1",
        diagnostics=DecisionDiagnostics(),
        context={"country": "US"},
    )

    report = ReportGenerator().generate(
        job=job,
        arms=_arms(job.job_id),
        decisions=[decision_a, decision_b],
        exposures=[
            ExposureCreate(
                workspace_id="ws-test",
                job_id=job.job_id,
                decision_id=decision_a.decision_id,
                unit_id="u1",
            ),
            ExposureCreate(
                workspace_id="ws-test",
                job_id=job.job_id,
                decision_id=decision_a.decision_id,
                unit_id="u1",
            ),
            ExposureCreate(
                workspace_id="ws-test",
                job_id=job.job_id,
                decision_id=decision_b.decision_id,
                unit_id="u2",
            ),
        ],
        outcomes=[
            OutcomeCreate(
                workspace_id="ws-test",
                job_id=job.job_id,
                decision_id=decision_a.decision_id,
                unit_id="u1",
                events=[OutcomeEvent(outcome_type="signup", value=1.0)],
            )
        ],
        guardrails=[],
    )

    summary_by_arm = {summary.arm_id: summary for summary in report.leaders}
    assert summary_by_arm["arm-a"].exposures == 2
    assert summary_by_arm["arm-b"].exposures == 1
    assert summary_by_arm["arm-a"].outcomes == 1
    assert summary_by_arm["arm-b"].outcomes == 0
