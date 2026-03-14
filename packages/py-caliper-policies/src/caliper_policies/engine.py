from __future__ import annotations

import hashlib
from dataclasses import dataclass

from caliper_core.models import (
    Arm,
    ArmState,
    AssignRequest,
    AssignResult,
    DecisionDiagnostics,
    Job,
    PolicyFamily,
)


@dataclass(frozen=True)
class WeightedArm:
    arm_id: str
    weight: float


class AssignmentError(ValueError):
    """Raised when assignment cannot be completed safely."""


class AssignmentEngine:
    """Policy selection engine for assignment decisions."""

    def assign(self, *, job: Job, request: AssignRequest, arms: list[Arm]) -> AssignResult:
        eligible_arms = self._eligible_arms(job=job, request=request, arms=arms)
        weighted, reason, fallback_used = self._policy_weights(job=job, arm_ids=eligible_arms)
        draw = self._deterministic_draw(
            job_id=job.job_id,
            unit_id=request.unit_id,
            idempotency_key=request.idempotency_key,
        )
        chosen = self._choose(weighted=weighted, draw=draw)

        return AssignResult(
            workspace_id=request.workspace_id,
            job_id=request.job_id,
            unit_id=request.unit_id,
            arm_id=chosen.arm_id,
            propensity=chosen.weight,
            policy_family=job.policy_spec.policy_family,
            policy_version=job.updated_at.strftime("%Y%m%d%H%M%S"),
            context_schema_version=job.policy_spec.context_schema_version,
            diagnostics=DecisionDiagnostics(
                scores={item.arm_id: item.weight for item in weighted},
                reason=reason,
                fallback_used=fallback_used,
            ),
            candidate_arms=[item.arm_id for item in weighted],
            context=request.context,
        )

    def _eligible_arms(self, *, job: Job, request: AssignRequest, arms: list[Arm]) -> list[str]:
        active_arms = [
            arm.arm_id
            for arm in arms
            if arm.workspace_id == request.workspace_id
            and arm.job_id == job.job_id
            and arm.state is ArmState.ACTIVE
        ]
        if request.candidate_arms is not None:
            candidate_set = set(request.candidate_arms)
            active_arms = [arm_id for arm_id in active_arms if arm_id in candidate_set]
        if not active_arms:
            msg = f"No eligible active arms for job '{job.job_id}'."
            raise AssignmentError(msg)
        return active_arms

    def _policy_weights(self, *, job: Job, arm_ids: list[str]) -> tuple[list[WeightedArm], str, bool]:
        if job.policy_spec.policy_family is PolicyFamily.EPSILON_GREEDY:
            weighted, fallback_used = self._epsilon_greedy_weights(job=job, arm_ids=arm_ids)
            return weighted, "epsilon_greedy_policy", fallback_used

        weighted, fallback_used = self._fixed_split_weights(job=job, arm_ids=arm_ids)
        return weighted, "fixed_split_weighted_draw", fallback_used

    def _fixed_split_weights(self, *, job: Job, arm_ids: list[str]) -> tuple[list[WeightedArm], bool]:
        configured = job.policy_spec.params.get("weights")
        if isinstance(configured, dict):
            raw = {arm_id: float(configured.get(arm_id, 0.0)) for arm_id in arm_ids}
            total = sum(raw.values())
            if total > 0:
                return (
                    [
                        WeightedArm(arm_id=arm_id, weight=raw[arm_id] / total)
                        for arm_id in arm_ids
                    ],
                    False,
                )

        equal = 1.0 / len(arm_ids)
        return ([WeightedArm(arm_id=arm_id, weight=equal) for arm_id in arm_ids], True)

    def _epsilon_greedy_weights(self, *, job: Job, arm_ids: list[str]) -> tuple[list[WeightedArm], bool]:
        epsilon_raw = job.policy_spec.params.get("epsilon", 0.1)
        try:
            epsilon = float(epsilon_raw)
        except (TypeError, ValueError):
            epsilon = 0.1
        epsilon = min(max(epsilon, 0.0), 1.0)

        value_estimates_raw = job.policy_spec.params.get("value_estimates")
        value_estimates = (
            {
                arm_id: float(value_estimates_raw.get(arm_id, 0.0))
                for arm_id in arm_ids
            }
            if isinstance(value_estimates_raw, dict)
            else {arm_id: 0.0 for arm_id in arm_ids}
        )

        best_value = max(value_estimates.values())
        best_arms = [arm_id for arm_id in arm_ids if value_estimates[arm_id] == best_value]

        explore_share = epsilon / len(arm_ids)
        exploit_share = (1.0 - epsilon) / len(best_arms)
        return (
            [
                WeightedArm(
                    arm_id=arm_id,
                    weight=explore_share + (exploit_share if arm_id in best_arms else 0.0),
                )
                for arm_id in arm_ids
            ],
            False,
        )

    def _deterministic_draw(self, *, job_id: str, unit_id: str, idempotency_key: str) -> float:
        digest = hashlib.sha256(f"{job_id}:{unit_id}:{idempotency_key}".encode()).digest()
        value = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return value / float(1 << 64)

    def _choose(self, *, weighted: list[WeightedArm], draw: float) -> WeightedArm:
        cumulative = 0.0
        for item in weighted:
            cumulative += item.weight
            if draw <= cumulative:
                return item
        return weighted[-1]
