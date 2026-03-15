from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from caliper_core.models import Arm, Job, PolicyFamily
from caliper_reward.engine import RewardRecord


@dataclass(frozen=True)
class PolicyUpdateResult:
    params: dict[str, Any]
    record_count: int
    updated_arm_ids: tuple[str, ...]


class PolicyUpdater:
    """Compute next-step policy parameters from observed reward records."""

    def update(
        self,
        *,
        job: Job,
        arms: list[Arm],
        records: list[RewardRecord],
    ) -> PolicyUpdateResult | None:
        if not records:
            return None

        arm_ids = tuple(sorted({arm.arm_id for arm in arms if arm.job_id == job.job_id}))
        if not arm_ids:
            arm_ids = tuple(sorted({record.arm_id for record in records}))

        if job.policy_spec.policy_family is PolicyFamily.EPSILON_GREEDY:
            return self._epsilon_greedy_update(job=job, arm_ids=arm_ids, records=records)
        if job.policy_spec.policy_family is PolicyFamily.UCB1:
            return self._ucb1_update(job=job, arm_ids=arm_ids, records=records)
        if job.policy_spec.policy_family is PolicyFamily.THOMPSON_SAMPLING:
            return self._thompson_sampling_update(job=job, arm_ids=arm_ids, records=records)

        # Contextual and fixed-split families are handled in later iterations.
        return None

    def _epsilon_greedy_update(
        self,
        *,
        job: Job,
        arm_ids: tuple[str, ...],
        records: list[RewardRecord],
    ) -> PolicyUpdateResult:
        params = dict(job.policy_spec.params)
        estimates_raw = params.get("value_estimates")
        pull_counts_raw = params.get("pull_counts")

        value_estimates = (
            {arm_id: float(estimates_raw.get(arm_id, 0.0)) for arm_id in arm_ids}
            if isinstance(estimates_raw, dict)
            else {arm_id: 0.0 for arm_id in arm_ids}
        )
        pull_counts = (
            {arm_id: max(int(pull_counts_raw.get(arm_id, 0)), 0) for arm_id in arm_ids}
            if isinstance(pull_counts_raw, dict)
            else {arm_id: 0 for arm_id in arm_ids}
        )

        updated_arms: set[str] = set()
        for record in records:
            if record.arm_id not in value_estimates:
                value_estimates[record.arm_id] = 0.0
                pull_counts[record.arm_id] = 0
            updated_arms.add(record.arm_id)
            prior_count = pull_counts[record.arm_id]
            next_count = prior_count + 1
            prior_mean = value_estimates[record.arm_id]
            value_estimates[record.arm_id] = prior_mean + (
                (record.reward - prior_mean) / next_count
            )
            pull_counts[record.arm_id] = next_count

        params["value_estimates"] = value_estimates
        params["pull_counts"] = pull_counts
        return PolicyUpdateResult(
            params=params,
            record_count=len(records),
            updated_arm_ids=tuple(sorted(updated_arms)),
        )

    def _ucb1_update(
        self,
        *,
        job: Job,
        arm_ids: tuple[str, ...],
        records: list[RewardRecord],
    ) -> PolicyUpdateResult:
        params = dict(job.policy_spec.params)
        means_raw = params.get("mean_rewards")
        pull_counts_raw = params.get("pull_counts")

        mean_rewards = (
            {arm_id: float(means_raw.get(arm_id, 0.0)) for arm_id in arm_ids}
            if isinstance(means_raw, dict)
            else {arm_id: 0.0 for arm_id in arm_ids}
        )
        pull_counts = (
            {arm_id: max(int(pull_counts_raw.get(arm_id, 0)), 0) for arm_id in arm_ids}
            if isinstance(pull_counts_raw, dict)
            else {arm_id: 0 for arm_id in arm_ids}
        )

        updated_arms: set[str] = set()
        for record in records:
            if record.arm_id not in mean_rewards:
                mean_rewards[record.arm_id] = 0.0
                pull_counts[record.arm_id] = 0
            updated_arms.add(record.arm_id)
            prior_count = pull_counts[record.arm_id]
            next_count = prior_count + 1
            prior_mean = mean_rewards[record.arm_id]
            mean_rewards[record.arm_id] = prior_mean + ((record.reward - prior_mean) / next_count)
            pull_counts[record.arm_id] = next_count

        params["mean_rewards"] = mean_rewards
        params["pull_counts"] = pull_counts
        return PolicyUpdateResult(
            params=params,
            record_count=len(records),
            updated_arm_ids=tuple(sorted(updated_arms)),
        )

    def _thompson_sampling_update(
        self,
        *,
        job: Job,
        arm_ids: tuple[str, ...],
        records: list[RewardRecord],
    ) -> PolicyUpdateResult:
        params = dict(job.policy_spec.params)
        alpha_raw = params.get("alpha")
        beta_raw = params.get("beta")

        alpha = (
            {arm_id: max(float(alpha_raw.get(arm_id, 1.0)), 1e-6) for arm_id in arm_ids}
            if isinstance(alpha_raw, dict)
            else {arm_id: 1.0 for arm_id in arm_ids}
        )
        beta = (
            {arm_id: max(float(beta_raw.get(arm_id, 1.0)), 1e-6) for arm_id in arm_ids}
            if isinstance(beta_raw, dict)
            else {arm_id: 1.0 for arm_id in arm_ids}
        )

        updated_arms: set[str] = set()
        for record in records:
            if record.arm_id not in alpha:
                alpha[record.arm_id] = 1.0
                beta[record.arm_id] = 1.0
            updated_arms.add(record.arm_id)
            success_mass = min(max(record.normalized_reward, 0.0), 1.0)
            alpha[record.arm_id] += success_mass
            beta[record.arm_id] += 1.0 - success_mass

        params["alpha"] = alpha
        params["beta"] = beta
        return PolicyUpdateResult(
            params=params,
            record_count=len(records),
            updated_arm_ids=tuple(sorted(updated_arms)),
        )
