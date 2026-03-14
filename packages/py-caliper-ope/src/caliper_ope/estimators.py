from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from caliper_ope.replay import ReplayRecord


class OPEEstimator(Protocol):
    """Future OPE estimator contract built on replay records."""

    def estimate(self, records: list[ReplayRecord]) -> float: ...


@dataclass(frozen=True)
class DatasetSummary:
    count: int
    average_reward: float


def summarize_dataset(records: list[ReplayRecord]) -> DatasetSummary:
    if not records:
        return DatasetSummary(count=0, average_reward=0.0)
    total_reward = sum(record.reward for record in records)
    return DatasetSummary(count=len(records), average_reward=total_reward / len(records))
