from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

from caliper_core.models import AssignResult, ObjectiveSpec, OutcomeCreate


class RewardFormulaError(ValueError):
    """Raised when reward formula evaluation fails validation."""


_ALLOWED_AST_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.Name,
    ast.Load,
    ast.Constant,
)


@dataclass(frozen=True)
class RewardRecord:
    workspace_id: str
    job_id: str
    decision_id: str
    unit_id: str
    arm_id: str
    propensity: float
    reward: float
    normalized_reward: float
    observed_at: datetime
    metrics: dict[str, float]


class RewardEngine:
    """Compute reward values and normalized policy-update datasets."""

    def evaluate_reward(
        self,
        *,
        objective_spec: ObjectiveSpec,
        outcome: OutcomeCreate,
    ) -> tuple[float, dict[str, float]]:
        metrics = self._collect_metrics(outcome)
        base_reward = self._evaluate_expression(objective_spec.reward_formula, metrics)

        penalty_total = 0.0
        for penalty_expr in objective_spec.penalties:
            penalty_value = self._evaluate_expression(penalty_expr, metrics)
            penalty_total += max(0.0, penalty_value)

        reward = base_reward - penalty_total
        return reward, metrics

    def build_policy_update_dataset(
        self,
        *,
        objective_spec: ObjectiveSpec,
        decisions: list[AssignResult],
        outcomes: list[OutcomeCreate],
    ) -> list[RewardRecord]:
        decisions_by_id = {decision.decision_id: decision for decision in decisions}
        records: list[RewardRecord] = []

        for outcome in outcomes:
            decision = decisions_by_id.get(outcome.decision_id)
            if decision is None:
                continue
            if not self._outcome_in_window(decision=decision, outcome=outcome):
                continue

            reward, metrics = self.evaluate_reward(
                objective_spec=objective_spec,
                outcome=outcome,
            )
            records.append(
                RewardRecord(
                    workspace_id=decision.workspace_id,
                    job_id=decision.job_id,
                    decision_id=decision.decision_id,
                    unit_id=decision.unit_id,
                    arm_id=decision.arm_id,
                    propensity=decision.propensity,
                    reward=reward,
                    normalized_reward=0.0,
                    observed_at=max(event.timestamp for event in outcome.events),
                    metrics=metrics,
                )
            )

        if not records:
            return []

        rewards = [record.reward for record in records]
        low = min(rewards)
        high = max(rewards)

        if high == low:
            return [
                RewardRecord(
                    workspace_id=record.workspace_id,
                    job_id=record.job_id,
                    decision_id=record.decision_id,
                    unit_id=record.unit_id,
                    arm_id=record.arm_id,
                    propensity=record.propensity,
                    reward=record.reward,
                    normalized_reward=1.0,
                    observed_at=record.observed_at,
                    metrics=record.metrics,
                )
                for record in records
            ]

        scale = high - low
        return [
            RewardRecord(
                workspace_id=record.workspace_id,
                job_id=record.job_id,
                decision_id=record.decision_id,
                unit_id=record.unit_id,
                arm_id=record.arm_id,
                propensity=record.propensity,
                reward=record.reward,
                normalized_reward=(record.reward - low) / scale,
                observed_at=record.observed_at,
                metrics=record.metrics,
            )
            for record in records
        ]

    def _outcome_in_window(self, *, decision: AssignResult, outcome: OutcomeCreate) -> bool:
        decision_timestamp = self._as_aware_utc(decision.timestamp)
        window_end = decision_timestamp + timedelta(hours=outcome.attribution_window.hours)
        return any(
            decision_timestamp <= self._as_aware_utc(event.timestamp) <= window_end
            for event in outcome.events
        )

    def _as_aware_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _collect_metrics(self, outcome: OutcomeCreate) -> dict[str, float]:
        metrics: dict[str, float] = {}
        numerator_by_metric: dict[str, float] = {}
        denominator_by_metric: dict[str, float] = {}

        for event in outcome.events:
            kind = event.metric_kind.strip().lower()
            metric = event.outcome_type
            if kind in {"value", "count"}:
                metrics[metric] = metrics.get(metric, 0.0) + event.value
                continue
            if kind == "rate":
                if event.denominator is None or event.denominator <= 0:
                    raise RewardFormulaError(
                        f"Rate metric '{metric}' requires a positive denominator"
                    )
                numerator_by_metric[metric] = numerator_by_metric.get(metric, 0.0) + (
                    event.value * event.denominator
                )
                denominator_by_metric[metric] = (
                    denominator_by_metric.get(metric, 0.0) + event.denominator
                )
                continue
            raise RewardFormulaError(f"Unsupported metric_kind: {event.metric_kind!r}")

        for metric, numerator in numerator_by_metric.items():
            denominator = denominator_by_metric[metric]
            metrics[metric] = numerator / denominator
            metrics[f"{metric}__numerator"] = numerator
            metrics[f"{metric}__denominator"] = denominator

        return metrics

    def _evaluate_expression(self, expression: str, metrics: dict[str, float]) -> float:
        parsed = ast.parse(expression, mode="eval")
        for node in ast.walk(parsed):
            if not isinstance(node, _ALLOWED_AST_NODES):
                raise RewardFormulaError(f"Unsupported syntax in expression: {expression!r}")
            if isinstance(node, ast.Name) and node.id not in metrics:
                metrics[node.id] = 0.0

        value = eval(compile(parsed, "<reward-formula>", "eval"), {"__builtins__": {}}, metrics)
        if not isinstance(value, (float, int)):
            raise RewardFormulaError(f"Expression did not produce a number: {expression!r}")

        numeric = float(value)
        if not isfinite(numeric):
            raise RewardFormulaError(f"Expression produced non-finite value: {expression!r}")
        return numeric
