from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from caliper_ope.replay import ReplayRecord


class OPEEstimator(Protocol):
    """Future OPE estimator contract built on replay records."""

    def estimate(self, records: list[ReplayRecord]) -> float: ...


@dataclass(frozen=True)
class DatasetSummary:
    count: int
    average_reward: float


@dataclass(frozen=True)
class OBPPreparedData:
    """Prepared OBP-compatible payload from replay records."""

    action_names: list[str]
    context_feature_names: list[str]
    bandit_feedback: dict[str, Any]
    evaluation_action_dist: list[list[list[float]]]


class OBPIntegrationError(RuntimeError):
    """Raised when OBP integration inputs are missing or invalid."""


def summarize_dataset(records: list[ReplayRecord]) -> DatasetSummary:
    if not records:
        return DatasetSummary(count=0, average_reward=0.0)
    total_reward = sum(record.reward for record in records)
    return DatasetSummary(count=len(records), average_reward=total_reward / len(records))


def prepare_obp_data(records: list[ReplayRecord]) -> OBPPreparedData:
    """Build OBP-ready bandit feedback + evaluation policy distribution.

    Expected replay context extension per record:
    - `obp_evaluation_probs`: mapping of arm_id -> probability under evaluation policy.

    The probabilities can omit arms not present in the candidate set; omitted arms default to 0.
    """
    if not records:
        raise OBPIntegrationError("cannot prepare OBP data from an empty replay dataset")

    action_name_set = {record.chosen_action for record in records}
    for record in records:
        raw_probs = record.context.get("obp_evaluation_probs")
        if isinstance(raw_probs, dict):
            action_name_set.update(str(arm_id) for arm_id in raw_probs)

    action_names = sorted(action_name_set)
    action_index = {name: idx for idx, name in enumerate(action_names)}

    context_feature_names = sorted(
        {
            key
            for record in records
            for key, value in record.context.items()
            if key != "obp_evaluation_probs" and isinstance(value, int | float)
        }
    )

    contexts: list[list[float]] = []
    actions: list[int] = []
    rewards: list[float] = []
    pscores: list[float] = []
    positions: list[int] = []
    eval_action_dist: list[list[list[float]]] = []

    for record in records:
        actions.append(action_index[record.chosen_action])
        rewards.append(float(record.reward))
        pscores.append(max(float(record.propensity), 1e-6))
        positions.append(0)
        row_context: list[float] = []
        for name in context_feature_names:
            value = record.context.get(name, 0.0)
            if isinstance(value, int | float):
                row_context.append(float(value))
            else:
                row_context.append(0.0)
        contexts.append(row_context)

        probs = _extract_eval_probs(record=record, action_names=action_names)
        eval_action_dist.append([[probs[name] for name in action_names]])

    bandit_feedback = {
        "n_rounds": len(records),
        "n_actions": len(action_names),
        "action": actions,
        "reward": rewards,
        "pscore": pscores,
        "position": positions,
        "context": contexts,
    }

    return OBPPreparedData(
        action_names=action_names,
        context_feature_names=context_feature_names,
        bandit_feedback=bandit_feedback,
        evaluation_action_dist=eval_action_dist,
    )


def estimate_policy_value_with_obp(
    records: list[ReplayRecord],
    *,
    estimator: str = "dr",
) -> float:
    """Estimate policy value using Open Bandit Pipeline estimators.

    Supported estimators:
    - `ipw` (InverseProbabilityWeighting)
    - `dr` (DoublyRobust)
    """
    prepared = prepare_obp_data(records)

    try:
        from obp.ope import (  # type: ignore[import-not-found]
            DoublyRobust,
            InverseProbabilityWeighting,
            OffPolicyEvaluation,
        )
    except ImportError as exc:  # pragma: no cover - exercised only when obp missing
        raise OBPIntegrationError(
            "OBP is not installed. Install with `uv pip install obp` to enable PV1-003 flows."
        ) from exc

    estimator_lower = estimator.lower()
    if estimator_lower == "ipw":
        ope_estimators = [InverseProbabilityWeighting()]
    elif estimator_lower == "dr":
        ope_estimators = [DoublyRobust()]
    else:
        raise OBPIntegrationError(f"unsupported OBP estimator: {estimator}")

    ope = OffPolicyEvaluation(
        bandit_feedback=prepared.bandit_feedback,
        ope_estimators=ope_estimators,
    )
    estimates = ope.estimate_policy_values(action_dist=prepared.evaluation_action_dist)
    result = estimates.get(ope_estimators[0].estimator_name)
    if result is None:
        raise OBPIntegrationError("OBP did not return an estimate for the selected estimator")
    return float(result)


def _extract_eval_probs(*, record: ReplayRecord, action_names: list[str]) -> dict[str, float]:
    raw = record.context.get("obp_evaluation_probs")
    if not isinstance(raw, dict):
        raise OBPIntegrationError(
            "missing context.obp_evaluation_probs for OBP evaluation on decision "
            f"{record.decision_id}"
        )

    parsed: dict[str, float] = {name: 0.0 for name in action_names}
    for key, value in raw.items():
        key_str = str(key)
        if key_str not in parsed:
            continue
        try:
            parsed[key_str] = max(float(value), 0.0)
        except (TypeError, ValueError):
            continue

    total = sum(parsed.values())
    if total <= 0:
        raise OBPIntegrationError(
            "obp_evaluation_probs must contain a positive probability mass for at least one arm"
        )

    return {key: value / total for key, value in parsed.items()}
