from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

import pytest
from caliper_ope import OBPIntegrationError, estimate_policy_value_with_obp, prepare_obp_data
from caliper_ope.replay import ReplayRecord


def _record(
    *,
    decision_id: str,
    chosen_action: str,
    reward: float,
    propensity: float,
    eval_probs: dict[str, float],
) -> ReplayRecord:
    now = datetime.now(tz=UTC)
    return ReplayRecord(
        workspace_id="ws",
        job_id="job",
        decision_id=decision_id,
        unit_id=f"user-{decision_id}",
        chosen_action=chosen_action,
        propensity=propensity,
        reward=reward,
        context={
            "country_us": 1.0,
            "device_mobile": 0.0,
            "obp_evaluation_probs": eval_probs,
        },
        assigned_at=now,
        first_exposed_at=now,
        latest_outcome_at=now,
    )


def test_prepare_obp_data_builds_feedback_and_action_dist() -> None:
    rows = [
        _record(
            decision_id="d1",
            chosen_action="arm-a",
            reward=1.0,
            propensity=0.7,
            eval_probs={"arm-a": 0.2, "arm-b": 0.8},
        ),
        _record(
            decision_id="d2",
            chosen_action="arm-b",
            reward=0.0,
            propensity=0.3,
            eval_probs={"arm-a": 0.6, "arm-b": 0.4},
        ),
    ]

    prepared = prepare_obp_data(rows)

    assert prepared.action_names == ["arm-a", "arm-b"]
    assert prepared.bandit_feedback["n_rounds"] == 2
    assert prepared.bandit_feedback["n_actions"] == 2
    assert prepared.bandit_feedback["action"] == [0, 1]
    assert prepared.bandit_feedback["reward"] == [1.0, 0.0]
    assert prepared.evaluation_action_dist == [
        [[0.2, 0.8]],
        [[0.6, 0.4]],
    ]


def test_prepare_obp_data_requires_eval_probs() -> None:
    row = _record(
        decision_id="d1",
        chosen_action="arm-a",
        reward=1.0,
        propensity=0.5,
        eval_probs={"arm-a": 1.0},
    )
    row.context.pop("obp_evaluation_probs")

    with pytest.raises(OBPIntegrationError, match="obp_evaluation_probs"):
        prepare_obp_data([row])


def test_estimate_policy_value_with_obp_uses_selected_estimator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _record(
            decision_id="d1",
            chosen_action="arm-a",
            reward=1.0,
            propensity=0.7,
            eval_probs={"arm-a": 0.3, "arm-b": 0.7},
        )
    ]

    obp_module = ModuleType("obp")
    ope_module = ModuleType("obp.ope")

    class _IPW:
        estimator_name = "ipw"

    class _DR:
        estimator_name = "dr"

    class _OffPolicyEvaluation:
        def __init__(self, *, bandit_feedback: dict[str, Any], ope_estimators: list[Any]) -> None:
            self.bandit_feedback = bandit_feedback
            self.ope_estimators = ope_estimators

        def estimate_policy_values(
            self, *, action_dist: list[list[list[float]]]
        ) -> dict[str, float]:
            assert self.bandit_feedback["n_rounds"] == 1
            assert action_dist == [[[0.3, 0.7]]]
            return {self.ope_estimators[0].estimator_name: 0.42}

    ope_module.InverseProbabilityWeighting = _IPW  # type: ignore[attr-defined]
    ope_module.DoublyRobust = _DR  # type: ignore[attr-defined]
    ope_module.OffPolicyEvaluation = _OffPolicyEvaluation  # type: ignore[attr-defined]
    obp_module.ope = ope_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "obp", obp_module)
    monkeypatch.setitem(sys.modules, "obp.ope", ope_module)

    estimate = estimate_policy_value_with_obp(rows, estimator="ipw")
    assert estimate == 0.42
