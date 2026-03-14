from __future__ import annotations

from collections import defaultdict

from caliper_core.models import (
    Arm,
    AssignResult,
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
        exposures: int,
        outcomes: list[OutcomeCreate],
        guardrails: list[dict[str, object]],
    ) -> ReportPayload:
        assignments_by_arm: dict[str, int] = defaultdict(int)
        for decision in decisions:
            assignments_by_arm[decision.arm_id] += 1

        reward_records = self._reward_engine.build_policy_update_dataset(
            objective_spec=job.objective_spec,
            decisions=decisions,
            outcomes=outcomes,
        )
        rewards_by_arm: dict[str, list[float]] = defaultdict(list)
        for record in reward_records:
            rewards_by_arm[record.arm_id].append(record.reward)

        total_assignments = max(1, len(decisions))
        summaries: list[ReportSummary] = []
        for arm in arms:
            rewards = rewards_by_arm.get(arm.arm_id, [])
            summaries.append(
                ReportSummary(
                    arm_id=arm.arm_id,
                    assignments=assignments_by_arm.get(arm.arm_id, 0),
                    exposures=exposures,
                    outcomes=sum(
                        1
                        for out in outcomes
                        if out.decision_id
                        in {d.decision_id for d in decisions if d.arm_id == arm.arm_id}
                    ),
                    avg_reward=(sum(rewards) / len(rewards)) if rewards else 0.0,
                    assignment_share=assignments_by_arm.get(arm.arm_id, 0) / total_assignments,
                )
            )

        leaders = sorted(summaries, key=lambda item: item.avg_reward, reverse=True)[:3]
        traffic_shifts = self._traffic_shifts(decisions=decisions)
        segment_findings = self._segment_findings(job=job, decisions=decisions)
        recommendations = self._recommendations(leaders=leaders, guardrails=guardrails)

        markdown = self._to_markdown(
            job=job,
            leaders=leaders,
            traffic_shifts=traffic_shifts,
            guardrails=guardrails,
            segment_findings=segment_findings,
            recommendations=recommendations,
        )
        html = self._to_html(markdown)

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
    ) -> list[Recommendation]:
        recs: list[Recommendation] = []
        if leaders:
            recs.append(
                Recommendation(
                    title="Promote current leader",
                    detail=f"Arm '{leaders[0].arm_id}' has the strongest observed average reward.",
                )
            )
        if guardrails:
            recs.append(
                Recommendation(
                    title="Review guardrail events",
                    detail=(
                        f"{len(guardrails)} guardrail events were recorded; "
                        "validate policy safety posture."
                    ),
                )
            )
        if not recs:
            recs.append(
                Recommendation(
                    title="Collect more data",
                    detail="Run additional traffic before making policy updates.",
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
    ) -> str:
        lines = [
            f"# Caliper report for {job.name}",
            "",
            "## Leaders",
        ]
        lines.extend(
            [
                "- "
                f"`{summary.arm_id}` avg_reward={summary.avg_reward:.4f} "
                f"share={summary.assignment_share:.2%}"
                for summary in leaders
            ]
            or ["- No leaders available yet."]
        )
        lines.append("")
        lines.append("## Traffic shifts")
        lines.extend(f"- {note}" for note in traffic_shifts)
        lines.append("")
        lines.append("## Guardrails")
        lines.extend(
            [
                f"- {event.get('metric', 'unknown')}: {event.get('status', 'unknown')}"
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

    def _to_html(self, markdown: str) -> str:
        return (
            "<html><body><pre>"
            + markdown.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "</pre></body></html>"
        )
