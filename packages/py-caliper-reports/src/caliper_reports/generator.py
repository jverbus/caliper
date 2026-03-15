from __future__ import annotations

from collections import defaultdict

from caliper_core.models import (
    Arm,
    AssignResult,
    ExposureCreate,
    Job,
    OutcomeCreate,
    Recommendation,
    ReportPayload,
    ReportSummary,
    SegmentFinding,
)
from caliper_reward.engine import RewardEngine


class ReportGenerator:
    """Generate deterministic report payloads in JSON + Markdown + HTML forms."""

    def __init__(self) -> None:
        self._reward_engine = RewardEngine()

    def generate(
        self,
        *,
        job: Job,
        arms: list[Arm],
        decisions: list[AssignResult],
        exposures: list[ExposureCreate],
        outcomes: list[OutcomeCreate],
        guardrails: list[dict[str, object]],
    ) -> ReportPayload:
        assignments_by_arm: dict[str, int] = defaultdict(int)
        decision_ids_by_arm: dict[str, set[str]] = defaultdict(set)
        for decision in decisions:
            assignments_by_arm[decision.arm_id] += 1
            decision_ids_by_arm[decision.arm_id].add(decision.decision_id)

        reward_records = self._reward_engine.build_policy_update_dataset(
            objective_spec=job.objective_spec,
            decisions=decisions,
            outcomes=outcomes,
        )
        rewards_by_arm: dict[str, list[float]] = defaultdict(list)
        for record in reward_records:
            rewards_by_arm[record.arm_id].append(record.reward)

        arm_by_decision_id = {decision.decision_id: decision.arm_id for decision in decisions}
        exposures_by_arm: dict[str, int] = defaultdict(int)
        for exposure in exposures:
            arm_id = arm_by_decision_id.get(exposure.decision_id)
            if arm_id is not None:
                exposures_by_arm[arm_id] += 1

        outcomes_by_arm: dict[str, int] = defaultdict(int)
        for outcome in outcomes:
            arm_id = arm_by_decision_id.get(outcome.decision_id)
            if arm_id is not None:
                outcomes_by_arm[arm_id] += 1

        total_assignments = max(1, len(decisions))
        summaries: list[ReportSummary] = []
        for arm in arms:
            rewards = rewards_by_arm.get(arm.arm_id, [])
            summaries.append(
                ReportSummary(
                    arm_id=arm.arm_id,
                    assignments=assignments_by_arm.get(arm.arm_id, 0),
                    exposures=exposures_by_arm.get(arm.arm_id, 0),
                    outcomes=outcomes_by_arm.get(arm.arm_id, 0),
                    avg_reward=(sum(rewards) / len(rewards)) if rewards else 0.0,
                    assignment_share=assignments_by_arm.get(arm.arm_id, 0) / total_assignments,
                )
            )

        leaders = sorted(summaries, key=lambda item: item.avg_reward, reverse=True)[:3]
        traffic_shifts = self._traffic_shifts(decisions=decisions)
        segment_findings = self._segment_findings(job=job, decisions=decisions)
        recommendations = self._recommendations(
            leaders=leaders,
            guardrails=guardrails,
            total_assignments=len(decisions),
        )

        markdown = self._to_markdown(
            job=job,
            leaders=leaders,
            traffic_shifts=traffic_shifts,
            guardrails=guardrails,
            segment_findings=segment_findings,
            recommendations=recommendations,
            total_assignments=len(decisions),
            total_exposures=len(exposures),
            total_outcomes=sum(len(item.events) for item in outcomes),
        )
        html = self._to_html(
            job=job,
            leaders=leaders,
            traffic_shifts=traffic_shifts,
            guardrails=guardrails,
            segment_findings=segment_findings,
            recommendations=recommendations,
            total_assignments=len(decisions),
            total_exposures=len(exposures),
            total_outcomes=sum(len(item.events) for item in outcomes),
        )

        return ReportPayload(
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            leaders=leaders,
            traffic_shifts=traffic_shifts,
            guardrails=guardrails,
            segment_findings=segment_findings,
            recommendations=recommendations,
            markdown=markdown,
            html=html,
        )

    def _traffic_shifts(self, *, decisions: list[AssignResult]) -> list[str]:
        if len(decisions) < 4:
            return ["Insufficient assignment history for traffic-shift analysis."]
        midpoint = len(decisions) // 2
        early = decisions[:midpoint]
        late = decisions[midpoint:]
        notes: list[str] = []
        for arm_id in sorted({decision.arm_id for decision in decisions}):
            early_count = sum(1 for decision in early if decision.arm_id == arm_id)
            late_count = sum(1 for decision in late if decision.arm_id == arm_id)
            delta = late_count - early_count
            if delta != 0:
                notes.append(
                    f"{arm_id}: {'+' if delta > 0 else ''}{delta} assignments in later window"
                )
        return notes or ["No meaningful traffic shift detected between early and late windows."]

    def _segment_findings(self, *, job: Job, decisions: list[AssignResult]) -> list[SegmentFinding]:
        dimensions = job.segment_spec.dimensions
        if not dimensions:
            return [SegmentFinding(segment="all", leader_arm_id=None, observations=len(decisions))]

        findings: list[SegmentFinding] = []
        for dimension in dimensions:
            counts: dict[str, int] = defaultdict(int)
            for decision in decisions:
                value = str(decision.context.get(dimension, "unknown"))
                counts[value] += 1
            if not counts:
                findings.append(
                    SegmentFinding(segment=dimension, leader_arm_id=None, observations=0)
                )
                continue
            top_value = max(counts.items(), key=lambda item: item[1])[0]
            findings.append(
                SegmentFinding(
                    segment=f"{dimension}={top_value}",
                    leader_arm_id=None,
                    observations=counts[top_value],
                )
            )
        return findings

    def _recommendations(
        self,
        *,
        leaders: list[ReportSummary],
        guardrails: list[dict[str, object]],
        total_assignments: int,
    ) -> list[Recommendation]:
        recs: list[Recommendation] = []
        if total_assignments >= 100:
            confidence = "high"
        elif total_assignments >= 30:
            confidence = "medium"
        else:
            confidence = "low"

        if leaders:
            leader = leaders[0]
            recs.append(
                Recommendation(
                    title="Promote current leader",
                    detail=(
                        f"Promote arm '{leader.arm_id}' cautiously "
                        f"({confidence} confidence): avg reward "
                        f"{leader.avg_reward:.4f} at "
                        f"{leader.assignment_share:.1%} traffic share."
                    ),
                )
            )

        if guardrails:
            recs.append(
                Recommendation(
                    title="Resolve guardrail alerts before scaling",
                    detail=(
                        f"{len(guardrails)} guardrail event(s) detected. "
                        "Keep rollout constrained until breached metrics return to expected ranges."
                    ),
                )
            )

        if not recs:
            recs.append(
                Recommendation(
                    title="Collect more evidence",
                    detail=(
                        "No clear leader yet. Continue traffic collection "
                        "before making policy updates or allocation changes."
                    ),
                )
            )
        return recs

    def _to_markdown(
        self,
        *,
        job: Job,
        leaders: list[ReportSummary],
        traffic_shifts: list[str],
        guardrails: list[dict[str, object]],
        segment_findings: list[SegmentFinding],
        recommendations: list[Recommendation],
        total_assignments: int,
        total_exposures: int,
        total_outcomes: int,
    ) -> str:
        lines = [
            f"# Caliper report: {job.name}",
            "",
            "## Summary",
            f"- Job ID: `{job.job_id}`",
            f"- Workspace: `{job.workspace_id}`",
            f"- Total assignments: {total_assignments}",
            f"- Total exposures: {total_exposures}",
            f"- Total outcome events: {total_outcomes}",
            "",
            "## Leaders",
            "| Arm | Avg reward | Assignment share | Assignments |",
            "| --- | ---: | ---: | ---: |",
        ]

        if leaders:
            lines.extend(
                [
                    "| "
                    f"`{summary.arm_id}` | {summary.avg_reward:.4f} | "
                    f"{summary.assignment_share:.2%} | {summary.assignments} |"
                    for summary in leaders
                ]
            )
        else:
            lines.append("| _none_ | 0.0000 | 0.00% | 0 |")

        lines.append("")
        lines.append("## Traffic shifts")
        lines.extend(f"- {note}" for note in traffic_shifts)
        lines.append("")
        lines.append("## Guardrails")
        lines.extend(
            [
                "- "
                f"`{event.get('metric', 'unknown')}` "
                f"status=`{event.get('status', 'unknown')}` "
                f"action=`{event.get('action', 'none')}`"
                for event in guardrails
            ]
            or ["- No guardrail events."]
        )
        lines.append("")
        lines.append("## Segment findings")
        lines.extend(
            [
                f"- {finding.segment} ({finding.observations} observations)"
                for finding in segment_findings
            ]
            or ["- No segment findings."]
        )
        lines.append("")
        lines.append("## Recommendations")
        lines.extend(f"- **{item.title}:** {item.detail}" for item in recommendations)
        return "\n".join(lines)

    def _to_html(
        self,
        *,
        job: Job,
        leaders: list[ReportSummary],
        traffic_shifts: list[str],
        guardrails: list[dict[str, object]],
        segment_findings: list[SegmentFinding],
        recommendations: list[Recommendation],
        total_assignments: int,
        total_exposures: int,
        total_outcomes: int,
    ) -> str:
        def escape(value: object) -> str:
            return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        leader_rows = (
            "".join(
                [
                    "<tr>"
                    f"<td><code>{escape(summary.arm_id)}</code></td>"
                    f"<td>{summary.avg_reward:.4f}</td>"
                    f"<td>{summary.assignment_share:.2%}</td>"
                    f"<td>{summary.assignments}</td>"
                    "</tr>"
                    for summary in leaders
                ]
            )
            or "<tr><td colspan='4'>No leaders available yet.</td></tr>"
        )

        traffic_items = "".join(f"<li>{escape(note)}</li>" for note in traffic_shifts)
        guardrail_items = (
            "".join(
                f"<li><code>{escape(event.get('metric', 'unknown'))}</code> "
                f"status=<code>{escape(event.get('status', 'unknown'))}</code> "
                f"action=<code>{escape(event.get('action', 'none'))}</code></li>"
                for event in guardrails
            )
            or "<li>No guardrail events.</li>"
        )
        segment_items = (
            "".join(
                f"<li>{escape(item.segment)} ({item.observations} observations)</li>"
                for item in segment_findings
            )
            or "<li>No segment findings.</li>"
        )
        recommendation_items = "".join(
            f"<li><strong>{escape(item.title)}:</strong> {escape(item.detail)}</li>"
            for item in recommendations
        )

        return (
            "<!doctype html>"
            "<html><head><meta charset='utf-8'><title>Caliper report</title></head><body>"
            f"<h1>Caliper report: {escape(job.name)}</h1>"
            "<h2>Summary</h2>"
            "<ul>"
            f"<li>Job ID: <code>{escape(job.job_id)}</code></li>"
            f"<li>Workspace: <code>{escape(job.workspace_id)}</code></li>"
            f"<li>Total assignments: {total_assignments}</li>"
            f"<li>Total exposures: {total_exposures}</li>"
            f"<li>Total outcome events: {total_outcomes}</li>"
            "</ul>"
            "<h2>Leaders</h2>"
            "<table border='1' cellspacing='0' cellpadding='6'>"
            "<thead><tr>"
            "<th>Arm</th><th>Avg reward</th>"
            "<th>Assignment share</th><th>Assignments</th>"
            "</tr></thead>"
            f"<tbody>{leader_rows}</tbody>"
            "</table>"
            "<h2>Traffic shifts</h2>"
            f"<ul>{traffic_items}</ul>"
            "<h2>Guardrails</h2>"
            f"<ul>{guardrail_items}</ul>"
            "<h2>Segment findings</h2>"
            f"<ul>{segment_items}</ul>"
            "<h2>Recommendations</h2>"
            f"<ul>{recommendation_items}</ul>"
            "</body></html>"
        )
