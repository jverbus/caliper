from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Any

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
        weighted, reason, fallback_used = self._policy_weights(
            job=job,
            request=request,
            arm_ids=eligible_arms,
        )
        draw = self._deterministic_draw(
            job_id=job.job_id,
            unit_id=request.unit_id,
            idempotency_key=request.idempotency_key,
        )
        chosen = self._choose(weighted=weighted, draw=draw)

        policy_version = str(
            job.policy_spec.params.get("policy_version", job.updated_at.strftime("%Y%m%d%H%M%S"))
        )

        return AssignResult(
            workspace_id=request.workspace_id,
            job_id=request.job_id,
            unit_id=request.unit_id,
            arm_id=chosen.arm_id,
            propensity=chosen.weight,
            policy_family=job.policy_spec.policy_family,
            policy_version=policy_version,
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
            and arm.state == ArmState.ACTIVE
        ]
        if request.candidate_arms is not None:
            candidate_set = set(request.candidate_arms)
            active_arms = [arm_id for arm_id in active_arms if arm_id in candidate_set]
        if not active_arms:
            msg = f"No eligible active arms for job '{job.job_id}'."
            raise AssignmentError(msg)
        return active_arms

    def _policy_weights(
        self,
        *,
        job: Job,
        request: AssignRequest,
        arm_ids: list[str],
    ) -> tuple[list[WeightedArm], str, bool]:
        if job.policy_spec.policy_family is PolicyFamily.EPSILON_GREEDY:
            weighted, fallback_used = self._epsilon_greedy_weights(job=job, arm_ids=arm_ids)
            return weighted, "epsilon_greedy_policy", fallback_used

        if job.policy_spec.policy_family is PolicyFamily.UCB1:
            weighted, fallback_used = self._ucb1_weights(job=job, arm_ids=arm_ids)
            return weighted, "ucb1_policy", fallback_used

        if job.policy_spec.policy_family is PolicyFamily.THOMPSON_SAMPLING:
            weighted, fallback_used = self._thompson_sampling_weights(
                job=job,
                request=request,
                arm_ids=arm_ids,
            )
            return weighted, "thompson_sampling_policy", fallback_used

        if job.policy_spec.policy_family is PolicyFamily.DISJOINT_LINUCB:
            weighted, fallback_used = self._disjoint_linucb_weights(
                job=job,
                request=request,
                arm_ids=arm_ids,
            )
            return weighted, "disjoint_linucb_policy", fallback_used

        weighted, fallback_used = self._fixed_split_weights(job=job, arm_ids=arm_ids)
        return weighted, "fixed_split_weighted_draw", fallback_used

    def _fixed_split_weights(
        self,
        *,
        job: Job,
        arm_ids: list[str],
    ) -> tuple[list[WeightedArm], bool]:
        configured = job.policy_spec.params.get("weights")
        if isinstance(configured, dict):
            raw = {arm_id: float(configured.get(arm_id, 0.0)) for arm_id in arm_ids}
            total = sum(raw.values())
            if total > 0:
                return (
                    [WeightedArm(arm_id=arm_id, weight=raw[arm_id] / total) for arm_id in arm_ids],
                    False,
                )

        equal = 1.0 / len(arm_ids)
        return ([WeightedArm(arm_id=arm_id, weight=equal) for arm_id in arm_ids], True)

    def _ucb1_weights(
        self,
        *,
        job: Job,
        arm_ids: list[str],
    ) -> tuple[list[WeightedArm], bool]:
        means_raw = job.policy_spec.params.get("mean_rewards")
        means = (
            {arm_id: float(means_raw.get(arm_id, 0.0)) for arm_id in arm_ids}
            if isinstance(means_raw, dict)
            else {arm_id: 0.0 for arm_id in arm_ids}
        )

        counts_raw = job.policy_spec.params.get("pull_counts")
        counts = (
            {arm_id: max(int(counts_raw.get(arm_id, 0)), 0) for arm_id in arm_ids}
            if isinstance(counts_raw, dict)
            else {arm_id: 0 for arm_id in arm_ids}
        )

        cold_start_arms = [arm_id for arm_id in arm_ids if counts[arm_id] <= 0]
        if cold_start_arms:
            cold_share = 1.0 / len(cold_start_arms)
            return (
                [
                    WeightedArm(
                        arm_id=arm_id,
                        weight=(cold_share if arm_id in cold_start_arms else 0.0),
                    )
                    for arm_id in arm_ids
                ],
                False,
            )

        exploration_raw = job.policy_spec.params.get("exploration_c", 1.0)
        try:
            exploration_c = max(float(exploration_raw), 0.0)
        except (TypeError, ValueError):
            exploration_c = 1.0

        total_pulls = sum(counts.values())
        log_total = math.log(max(total_pulls, 1))
        scores = {
            arm_id: means[arm_id] + exploration_c * math.sqrt((2.0 * log_total) / counts[arm_id])
            for arm_id in arm_ids
        }

        score_total = sum(scores.values())
        if score_total > 0:
            return (
                [
                    WeightedArm(arm_id=arm_id, weight=scores[arm_id] / score_total)
                    for arm_id in arm_ids
                ],
                False,
            )

        equal = 1.0 / len(arm_ids)
        return ([WeightedArm(arm_id=arm_id, weight=equal) for arm_id in arm_ids], True)

    def _thompson_sampling_weights(
        self,
        *,
        job: Job,
        request: AssignRequest,
        arm_ids: list[str],
    ) -> tuple[list[WeightedArm], bool]:
        alpha_raw = job.policy_spec.params.get("alpha")
        beta_raw = job.policy_spec.params.get("beta")

        alphas = (
            {arm_id: max(float(alpha_raw.get(arm_id, 1.0)), 1e-6) for arm_id in arm_ids}
            if isinstance(alpha_raw, dict)
            else {arm_id: 1.0 for arm_id in arm_ids}
        )
        betas = (
            {arm_id: max(float(beta_raw.get(arm_id, 1.0)), 1e-6) for arm_id in arm_ids}
            if isinstance(beta_raw, dict)
            else {arm_id: 1.0 for arm_id in arm_ids}
        )

        seed_salt = str(job.policy_spec.params.get("seed_salt", ""))
        seed_material = f"{job.job_id}:{request.unit_id}:{request.idempotency_key}:{seed_salt}"
        samples = {
            arm_id: self._deterministic_beta_sample(
                arm_id=arm_id,
                alpha=alphas[arm_id],
                beta=betas[arm_id],
                seed_material=seed_material,
            )
            for arm_id in arm_ids
        }
        sample_total = sum(samples.values())
        if sample_total > 0:
            return (
                [
                    WeightedArm(arm_id=arm_id, weight=samples[arm_id] / sample_total)
                    for arm_id in arm_ids
                ],
                False,
            )

        equal = 1.0 / len(arm_ids)
        return ([WeightedArm(arm_id=arm_id, weight=equal) for arm_id in arm_ids], True)

    def _disjoint_linucb_weights(
        self,
        *,
        job: Job,
        request: AssignRequest,
        arm_ids: list[str],
    ) -> tuple[list[WeightedArm], bool]:
        params = job.policy_spec.params
        alpha_raw = params.get("alpha", 1.0)
        try:
            alpha = max(float(alpha_raw), 0.0)
        except (TypeError, ValueError):
            alpha = 1.0

        feature_order = params.get("feature_order")
        feature_dim_raw = params.get("feature_dim")
        feature_vector = self._linucb_feature_vector(
            context=request.context,
            feature_order=feature_order if isinstance(feature_order, list) else None,
            feature_dim=feature_dim_raw,
        )
        if feature_vector is None:
            equal = 1.0 / len(arm_ids)
            return ([WeightedArm(arm_id=arm_id, weight=equal) for arm_id in arm_ids], True)

        state = params.get("linucb_state")
        scores: dict[str, float] = {}
        for arm_id in arm_ids:
            a_matrix, b_vector = self._linucb_arm_state(
                state=state,
                arm_id=arm_id,
                dimension=len(feature_vector),
            )
            a_inv = self._invert_matrix(a_matrix)
            theta = self._matvec(a_inv, b_vector)
            exploit = self._dot(feature_vector, theta)
            uncertainty = self._dot(feature_vector, self._matvec(a_inv, feature_vector))
            explore = alpha * math.sqrt(max(uncertainty, 0.0))
            scores[arm_id] = exploit + explore

        best_score = max(scores.values())
        winners = [arm_id for arm_id, score in scores.items() if math.isclose(score, best_score)]
        winner_share = 1.0 / len(winners)
        return (
            [
                WeightedArm(
                    arm_id=arm_id,
                    weight=(winner_share if arm_id in winners else 0.0),
                )
                for arm_id in arm_ids
            ],
            False,
        )

    def _linucb_feature_vector(
        self,
        *,
        context: dict[str, Any],
        feature_order: list[Any] | None,
        feature_dim: Any,
    ) -> list[float] | None:
        features = context.get("features")
        if isinstance(features, list):
            try:
                return [float(value) for value in features]
            except (TypeError, ValueError):
                return None

        if isinstance(features, dict) and feature_order:
            vector: list[float] = []
            for key in feature_order:
                if key not in features:
                    return None
                try:
                    vector.append(float(features[key]))
                except (TypeError, ValueError):
                    return None
            return vector

        if isinstance(feature_dim, int) and feature_dim > 0:
            return [0.0] * feature_dim
        return None

    def _linucb_arm_state(
        self,
        *,
        state: Any,
        arm_id: str,
        dimension: int,
    ) -> tuple[list[list[float]], list[float]]:
        identity = [
            [1.0 if idx == jdx else 0.0 for jdx in range(dimension)] for idx in range(dimension)
        ]
        zeros = [0.0] * dimension

        if not isinstance(state, dict):
            return identity, zeros
        raw = state.get(arm_id)
        if not isinstance(raw, dict):
            return identity, zeros

        raw_a = raw.get("a")
        raw_b = raw.get("b")
        if not isinstance(raw_a, list) or not isinstance(raw_b, list) or len(raw_b) != dimension:
            return identity, zeros

        try:
            parsed_a = [[float(cell) for cell in row] for row in raw_a]
            parsed_b = [float(value) for value in raw_b]
        except (TypeError, ValueError):
            return identity, zeros

        if len(parsed_a) != dimension or any(len(row) != dimension for row in parsed_a):
            return identity, zeros
        return parsed_a, parsed_b

    def _invert_matrix(self, matrix: list[list[float]]) -> list[list[float]]:
        dim = len(matrix)
        augmented = [
            row[:] + [1.0 if idx == jdx else 0.0 for jdx in range(dim)]
            for idx, row in enumerate(matrix)
        ]

        for pivot in range(dim):
            max_row = max(range(pivot, dim), key=lambda idx: abs(augmented[idx][pivot]))
            if abs(augmented[max_row][pivot]) < 1e-12:
                return [[1.0 if idx == jdx else 0.0 for jdx in range(dim)] for idx in range(dim)]
            augmented[pivot], augmented[max_row] = augmented[max_row], augmented[pivot]
            pivot_value = augmented[pivot][pivot]
            augmented[pivot] = [value / pivot_value for value in augmented[pivot]]

            for row_idx in range(dim):
                if row_idx == pivot:
                    continue
                factor = augmented[row_idx][pivot]
                augmented[row_idx] = [
                    current - (factor * pivot_value)
                    for current, pivot_value in zip(
                        augmented[row_idx],
                        augmented[pivot],
                        strict=True,
                    )
                ]

        return [row[dim:] for row in augmented]

    def _matvec(self, matrix: list[list[float]], vector: list[float]) -> list[float]:
        return [sum(cell * vector[col] for col, cell in enumerate(row)) for row in matrix]

    def _dot(self, left: list[float], right: list[float]) -> float:
        return sum(lhs * rhs for lhs, rhs in zip(left, right, strict=True))

    def _epsilon_greedy_weights(
        self,
        *,
        job: Job,
        arm_ids: list[str],
    ) -> tuple[list[WeightedArm], bool]:
        epsilon_raw = job.policy_spec.params.get("epsilon", 0.1)
        try:
            epsilon = float(epsilon_raw)
        except (TypeError, ValueError):
            epsilon = 0.1
        epsilon = min(max(epsilon, 0.0), 1.0)

        value_estimates_raw = job.policy_spec.params.get("value_estimates")
        value_estimates = (
            {arm_id: float(value_estimates_raw.get(arm_id, 0.0)) for arm_id in arm_ids}
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

    def _deterministic_beta_sample(
        self,
        *,
        arm_id: str,
        alpha: float,
        beta: float,
        seed_material: str,
    ) -> float:
        digest = hashlib.sha256(f"{seed_material}:{arm_id}".encode()).digest()
        seed = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return random.Random(seed).betavariate(alpha, beta)

    def _choose(self, *, weighted: list[WeightedArm], draw: float) -> WeightedArm:
        cumulative = 0.0
        for item in weighted:
            cumulative += item.weight
            if draw <= cumulative:
                return item
        return weighted[-1]
