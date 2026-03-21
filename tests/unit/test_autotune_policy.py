from __future__ import annotations

from apps.api.services.autotune_policy import (
    autotune_disposition,
    derived_complexity_score,
)


def test_policy_disposition_keeps_when_delta_over_threshold_and_penalty_ok() -> None:
    keep_discard, reason = autotune_disposition(
        candidate_score=0.71,
        baseline_score=0.68,
        complexity_penalty=0.03,
        hard_fail_code=None,
    )
    assert keep_discard == "keep"
    assert reason == "kept: delta 0.0300 > 0.0100 with complexity penalty 0.0300"


def test_policy_disposition_discards_when_complexity_penalty_too_high() -> None:
    keep_discard, reason = autotune_disposition(
        candidate_score=0.75,
        baseline_score=0.70,
        complexity_penalty=0.081,
        hard_fail_code=None,
    )
    assert keep_discard == "discard"
    assert reason == "discarded: complexity penalty 0.0810 > max 0.0800"


def test_policy_complexity_score_uses_derived_inputs_without_dropping_declared_floor() -> None:
    complexity, inputs = derived_complexity_score(
        candidate_content={
            "prompt": "x" * 500,
            "tone": "urgent",
            "template": "A",
            "audience": "new-users",
        },
        baseline_content={"prompt": "baseline"},
        declared_complexity_score=0.2,
    )
    assert complexity >= 0.2
    assert inputs["changed_fields"] >= 3
