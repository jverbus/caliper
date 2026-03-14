from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from caliper_core.models import GuardrailAction, GuardrailEvent, GuardrailSpec

from .engine import RewardRecord


@dataclass(frozen=True)
class GuardrailEvaluation:
    event: GuardrailEvent
    target_arm_id: str | None = None


class GuardrailEngine:
    """Evaluate guardrail rules against reward records."""

    def evaluate(
        self,
        *,
        workspace_id: str,
        job_id: str,
        guardrail_spec: GuardrailSpec,
        records: list[RewardRecord],
    ) -> list[GuardrailEvaluation]:
        evaluations: list[GuardrailEvaluation] = []
        for rule in guardrail_spec.rules:
            metric_value = self._aggregate_metric(records, rule.metric)
            if metric_value is None:
                continue
            if not self._compare(metric_value, rule.op, rule.threshold):
                continue

            target_arm_id = self._target_arm_for_metric(records, rule.metric)
            evaluations.append(
                GuardrailEvaluation(
                    event=GuardrailEvent(
                        workspace_id=workspace_id,
                        job_id=job_id,
                        metric=rule.metric,
                        status="breach",
                        action=rule.action,
                        metadata={
                            "operator": rule.op,
                            "threshold": rule.threshold,
                            "observed": metric_value,
                            "target_arm_id": target_arm_id,
                        },
                    ),
                    target_arm_id=target_arm_id,
                )
            )

        return evaluations

    def _aggregate_metric(self, records: list[RewardRecord], metric: str) -> float | None:
        values = [
            value
            for record in records
            if (value := record.metrics.get(metric)) is not None
        ]
        if not values:
            return None
        aggregate = sum(values) / len(values)
        if not isfinite(aggregate):
            return None
        return aggregate

    def _target_arm_for_metric(self, records: list[RewardRecord], metric: str) -> str | None:
        by_arm: dict[str, list[float]] = {}
        for record in records:
            if metric not in record.metrics:
                continue
            by_arm.setdefault(record.arm_id, []).append(record.metrics[metric])

        if not by_arm:
            return None

        # Demotions/caps should target the highest-risk arm by average metric value.
        ranked = sorted(
            ((sum(values) / len(values), arm_id) for arm_id, values in by_arm.items() if values),
            reverse=True,
        )
        return ranked[0][1] if ranked else None

    def _compare(self, observed: float, op: str, threshold: float) -> bool:
        if op == ">":
            return observed > threshold
        if op == ">=":
            return observed >= threshold
        if op == "<":
            return observed < threshold
        if op == "<=":
            return observed <= threshold
        if op == "==":
            return observed == threshold
        if op == "!=":
            return observed != threshold
        raise ValueError(f"Unsupported guardrail operator: {op}")


def action_requires_arm_target(action: GuardrailAction) -> bool:
    return action in {GuardrailAction.CAP, GuardrailAction.DEMOTE}
