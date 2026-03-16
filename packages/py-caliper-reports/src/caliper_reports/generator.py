from __future__ import annotations

import random
from bisect import bisect_left
from collections import defaultdict
from hashlib import sha256

from caliper_core.models import (
    Arm,
    AssignResult,
    ExposureCreate,
    Job,
    LeaderSignificanceDiagnostics,
    OutcomeCreate,
    Recommendation,
    ReportPayload,
    ReportSummary,
    SegmentFinding,
    SRMDiagnostics,
    StatisticalDiagnostics,
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
        diagnostics = self._statistical_diagnostics(
            job=job,
            arms=arms,
            assignments_by_arm=assignments_by_arm,
            rewards_by_arm=rewards_by_arm,
            total_assignments=len(decisions),
        )
        recommendations = self._recommendations(
            leaders=leaders,
            guardrails=guardrails,
            total_assignments=len(decisions),
            diagnostics=diagnostics,
        )

        markdown = self._to_markdown(
            job=job,
            leaders=leaders,
            traffic_shifts=traffic_shifts,
            guardrails=guardrails,
            segment_findings=segment_findings,
            recommendations=recommendations,
            diagnostics=diagnostics,
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
            diagnostics=diagnostics,
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
            statistics=diagnostics,
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

    def _statistical_diagnostics(
        self,
        *,
        job: Job,
        arms: list[Arm],
        assignments_by_arm: dict[str, int],
        rewards_by_arm: dict[str, list[float]],
        total_assignments: int,
    ) -> StatisticalDiagnostics:
        seed_material = f"{job.job_id}:{total_assignments}:{len(arms)}"
        seed = int(sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)

        srm = self._srm_diagnostics(
            job=job,
            arms=arms,
            assignments_by_arm=assignments_by_arm,
            total_assignments=total_assignments,
            rng=rng,
        )
        leader_significance = self._leader_significance(
            rewards_by_arm=rewards_by_arm,
            rng=rng,
        )

        return StatisticalDiagnostics(
            srm=srm,
            leader_significance=leader_significance,
        )

    def _srm_diagnostics(
        self,
        *,
        job: Job,
        arms: list[Arm],
        assignments_by_arm: dict[str, int],
        total_assignments: int,
        rng: random.Random,
    ) -> SRMDiagnostics:
        expected = self._expected_assignment_share(job=job, arms=arms)
        observed_assignments = {
            arm.arm_id: assignments_by_arm.get(arm.arm_id, 0)
            for arm in sorted(arms, key=lambda item: item.arm_id)
        }

        if expected is None:
            return SRMDiagnostics(
                applicable=False,
                reason="SRM is only computed for fixed_split jobs with explicit positive weights.",
                observed_assignments=observed_assignments,
            )

        if total_assignments <= 0:
            return SRMDiagnostics(
                applicable=False,
                reason="No assignments yet.",
                expected_assignment_share=expected,
                observed_assignments=observed_assignments,
            )

        arm_ids = sorted(expected)
        expected_probs = [expected[arm_id] for arm_id in arm_ids]
        observed = [assignments_by_arm.get(arm_id, 0) for arm_id in arm_ids]
        observed_chi_square = self._chi_square_statistic(
            observed=observed,
            expected_probs=expected_probs,
            total=total_assignments,
        )

        if observed_chi_square is None:
            return SRMDiagnostics(
                applicable=False,
                reason="Expected split has zero probability mass.",
                expected_assignment_share=expected,
                observed_assignments=observed_assignments,
            )

        iterations = 2000
        extreme_count = 0
        for _ in range(iterations):
            sampled = self._sample_multinomial(
                total=total_assignments,
                expected_probs=expected_probs,
                rng=rng,
            )
            sampled_chi_square = self._chi_square_statistic(
                observed=sampled,
                expected_probs=expected_probs,
                total=total_assignments,
            )
            if sampled_chi_square is not None and sampled_chi_square >= observed_chi_square:
                extreme_count += 1

        p_value = (extreme_count + 1) / (iterations + 1)
        threshold = 0.01
        return SRMDiagnostics(
            applicable=True,
            expected_assignment_share=expected,
            observed_assignments=observed_assignments,
            chi_square=observed_chi_square,
            p_value=p_value,
            threshold=threshold,
            alert=p_value < threshold,
        )

    def _expected_assignment_share(self, *, job: Job, arms: list[Arm]) -> dict[str, float] | None:
        if job.policy_spec.policy_family.value != "fixed_split":
            return None

        raw_weights = job.policy_spec.params.get("weights")
        if not isinstance(raw_weights, dict):
            return None

        arm_ids = [arm.arm_id for arm in arms]
        positive_weights: dict[str, float] = {}
        for arm_id in arm_ids:
            raw_value = raw_weights.get(arm_id)
            if not isinstance(raw_value, int | float):
                continue
            numeric = float(raw_value)
            if numeric > 0:
                positive_weights[arm_id] = numeric

        if not positive_weights:
            return None

        total = sum(positive_weights.values())
        if total <= 0:
            return None

        return {arm_id: weight / total for arm_id, weight in positive_weights.items()}

    def _chi_square_statistic(
        self,
        *,
        observed: list[int],
        expected_probs: list[float],
        total: int,
    ) -> float | None:
        statistic = 0.0
        for count, probability in zip(observed, expected_probs, strict=False):
            expected_count = total * probability
            if expected_count <= 0:
                return None
            statistic += ((count - expected_count) ** 2) / expected_count
        return statistic

    def _sample_multinomial(
        self,
        *,
        total: int,
        expected_probs: list[float],
        rng: random.Random,
    ) -> list[int]:
        counts = [0 for _ in expected_probs]
        cumulative: list[float] = []
        running = 0.0
        for probability in expected_probs:
            running += probability
            cumulative.append(running)

        for _ in range(total):
            draw = rng.random()
            idx = min(bisect_left(cumulative, draw), len(counts) - 1)
            counts[idx] += 1
        return counts

    def _leader_significance(
        self,
        *,
        rewards_by_arm: dict[str, list[float]],
        rng: random.Random,
    ) -> LeaderSignificanceDiagnostics:
        candidates = [(arm_id, values) for arm_id, values in rewards_by_arm.items() if values]
        if len(candidates) < 2:
            return LeaderSignificanceDiagnostics(
                applicable=False,
                reason="Need outcome-derived rewards for at least two arms.",
            )

        ranked = sorted(
            candidates,
            key=lambda item: (sum(item[1]) / len(item[1]), len(item[1])),
            reverse=True,
        )
        leader_arm_id, leader_rewards = ranked[0]
        challenger_arm_id, challenger_rewards = ranked[1]

        if len(leader_rewards) < 2 or len(challenger_rewards) < 2:
            return LeaderSignificanceDiagnostics(
                applicable=False,
                reason=(
                    "Need at least two reward observations per top arm for significance testing."
                ),
                leader_arm_id=leader_arm_id,
                challenger_arm_id=challenger_arm_id,
                sample_sizes={
                    leader_arm_id: len(leader_rewards),
                    challenger_arm_id: len(challenger_rewards),
                },
            )

        leader_mean = sum(leader_rewards) / len(leader_rewards)
        challenger_mean = sum(challenger_rewards) / len(challenger_rewards)
        observed_diff = leader_mean - challenger_mean

        combined = [*leader_rewards, *challenger_rewards]
        leader_size = len(leader_rewards)
        iterations = 2000
        extreme_count = 0

        for _ in range(iterations):
            shuffled = list(combined)
            rng.shuffle(shuffled)
            perm_leader = shuffled[:leader_size]
            perm_challenger = shuffled[leader_size:]
            perm_diff = (sum(perm_leader) / len(perm_leader)) - (
                sum(perm_challenger) / len(perm_challenger)
            )
            if abs(perm_diff) >= abs(observed_diff):
                extreme_count += 1

        p_value = (extreme_count + 1) / (iterations + 1)
        alpha = 0.05
        return LeaderSignificanceDiagnostics(
            applicable=True,
            leader_arm_id=leader_arm_id,
            challenger_arm_id=challenger_arm_id,
            leader_mean=leader_mean,
            challenger_mean=challenger_mean,
            observed_diff=observed_diff,
            p_value=p_value,
            alpha=alpha,
            statistically_significant=p_value < alpha,
            iterations=iterations,
            sample_sizes={
                leader_arm_id: len(leader_rewards),
                challenger_arm_id: len(challenger_rewards),
            },
        )

    def _recommendations(
        self,
        *,
        leaders: list[ReportSummary],
        guardrails: list[dict[str, object]],
        total_assignments: int,
        diagnostics: StatisticalDiagnostics,
    ) -> list[Recommendation]:
        recs: list[Recommendation] = []
        if total_assignments >= 100:
            confidence = "high"
        elif total_assignments >= 30:
            confidence = "medium"
        else:
            confidence = "low"

        leader_significance = diagnostics.leader_significance
        if leaders:
            leader = leaders[0]
            significance_note = ""
            if leader_significance.applicable and leader_significance.p_value is not None:
                verdict = (
                    "statistically significant"
                    if leader_significance.statistically_significant
                    else "not yet statistically significant"
                )
                significance_note = (
                    f" Leader-vs-runner-up p-value={leader_significance.p_value:.4f} "
                    f"({verdict}, alpha={leader_significance.alpha:.2f})."
                )
            recs.append(
                Recommendation(
                    title="Promote current leader",
                    detail=(
                        f"Promote arm '{leader.arm_id}' cautiously "
                        f"({confidence} confidence): avg reward "
                        f"{leader.avg_reward:.4f} at "
                        f"{leader.assignment_share:.1%} traffic share."
                        f"{significance_note}"
                    ),
                )
            )

        srm = diagnostics.srm
        if srm.applicable and srm.alert:
            recs.append(
                Recommendation(
                    title="Investigate SRM before trust decisions",
                    detail=(
                        "Sample-ratio mismatch detected "
                        f"(p={srm.p_value:.4f}, threshold={srm.threshold:.2f}). "
                        "Check assignment plumbing, eligibility filters, and logging integrity."
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
        diagnostics: StatisticalDiagnostics,
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
        lines.append("## Statistical diagnostics")

        srm = diagnostics.srm
        if srm.applicable and srm.p_value is not None:
            expected_share = ", ".join(
                f"{arm_id}={share:.1%}"
                for arm_id, share in sorted(srm.expected_assignment_share.items())
            )
            observed = ", ".join(
                f"{arm_id}={count}" for arm_id, count in sorted(srm.observed_assignments.items())
            )
            lines.append(
                "- SRM check: "
                f"chi_square={srm.chi_square:.4f}, p_value={srm.p_value:.4f}, "
                f"threshold={srm.threshold:.2f}, alert={'yes' if srm.alert else 'no'}"
            )
            lines.append(f"- SRM expected split: {expected_share or 'n/a'}")
            lines.append(f"- SRM observed assignments: {observed or 'n/a'}")
        else:
            lines.append(f"- SRM check: not applicable ({srm.reason or 'insufficient data'})")

        leader = diagnostics.leader_significance
        if (
            leader.applicable
            and leader.p_value is not None
            and leader.leader_arm_id is not None
            and leader.challenger_arm_id is not None
        ):
            significance_flag = "yes" if leader.statistically_significant else "no"
            lines.append(
                "- Leader significance: "
                f"{leader.leader_arm_id} vs {leader.challenger_arm_id}, "
                f"diff={leader.observed_diff:.4f}, p_value={leader.p_value:.4f}, "
                f"significant_at_{leader.alpha:.2f}={significance_flag}"
            )
        else:
            lines.append(
                f"- Leader significance: not applicable ({leader.reason or 'insufficient data'})"
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
        diagnostics: StatisticalDiagnostics,
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

        srm = diagnostics.srm
        if srm.applicable and srm.p_value is not None:
            expected_share = ", ".join(
                f"{arm_id}={share:.1%}"
                for arm_id, share in sorted(srm.expected_assignment_share.items())
            )
            observed = ", ".join(
                f"{arm_id}={count}" for arm_id, count in sorted(srm.observed_assignments.items())
            )
            srm_item = (
                "<li>SRM check: "
                f"chi_square={srm.chi_square:.4f}, p_value={srm.p_value:.4f}, "
                f"threshold={srm.threshold:.2f}, alert={'yes' if srm.alert else 'no'}"
                "</li>"
                f"<li>SRM expected split: {escape(expected_share or 'n/a')}</li>"
                f"<li>SRM observed assignments: {escape(observed or 'n/a')}</li>"
            )
        else:
            srm_item = (
                f"<li>SRM check: not applicable ({escape(srm.reason or 'insufficient data')})</li>"
            )

        leader = diagnostics.leader_significance
        if (
            leader.applicable
            and leader.p_value is not None
            and leader.leader_arm_id is not None
            and leader.challenger_arm_id is not None
        ):
            leader_item = (
                "<li>Leader significance: "
                f"{escape(leader.leader_arm_id)} vs {escape(leader.challenger_arm_id)}, "
                f"diff={leader.observed_diff:.4f}, p_value={leader.p_value:.4f}, "
                f"significant_at_{leader.alpha:.2f}="
                f"{'yes' if leader.statistically_significant else 'no'}"
                "</li>"
            )
        else:
            leader_item = (
                "<li>Leader significance: not applicable "
                f"({escape(leader.reason or 'insufficient data')})</li>"
            )

        statistics_items = f"{srm_item}{leader_item}"

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
            "<h2>Statistical diagnostics</h2>"
            f"<ul>{statistics_items}</ul>"
            "<h2>Recommendations</h2>"
            f"<ul>{recommendation_items}</ul>"
            "</body></html>"
        )
