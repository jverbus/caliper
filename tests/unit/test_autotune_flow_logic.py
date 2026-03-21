from __future__ import annotations

from apps.api.main import _autotune_disposition, _derived_complexity_score


def test_autotune_disposition_keeps_when_delta_over_threshold_and_penalty_ok() -> None:
    keep_discard, reason = _autotune_disposition(
        candidate_score=0.71,
        baseline_score=0.68,
        complexity_penalty=0.03,
        hard_fail_code=None,
    )
    assert keep_discard == "keep"
    assert reason == "kept: delta 0.0300 > 0.0100 with complexity penalty 0.0300"


def test_autotune_disposition_discards_when_delta_below_threshold() -> None:
    keep_discard, reason = _autotune_disposition(
        candidate_score=0.685,
        baseline_score=0.68,
        complexity_penalty=0.01,
        hard_fail_code=None,
    )
    assert keep_discard == "discard"
    assert reason == "discarded: delta 0.0050 <= keep threshold 0.0100"


def test_autotune_disposition_discards_on_complexity_penalty_cap() -> None:
    keep_discard, reason = _autotune_disposition(
        candidate_score=0.75,
        baseline_score=0.70,
        complexity_penalty=0.081,
        hard_fail_code=None,
    )
    assert keep_discard == "discard"
    assert reason == "discarded: complexity penalty 0.0810 > max 0.0800"


def test_autotune_disposition_discards_on_hard_fail() -> None:
    keep_discard, reason = _autotune_disposition(
        candidate_score=1.0,
        baseline_score=0.0,
        complexity_penalty=0.0,
        hard_fail_code="ROLLBACK_RECOMMENDATION",
    )
    assert keep_discard == "discard"
    assert reason == "discarded: hard fail (ROLLBACK_RECOMMENDATION)"


def test_derived_complexity_score_is_never_below_declared() -> None:
    complexity, inputs = _derived_complexity_score(
        candidate_content={"prompt": "tiny tweak"},
        baseline_content={"prompt": "tiny tweak"},
        declared_complexity_score=0.4,
    )
    assert complexity >= 0.4
    assert "changed_fields" in inputs


def test_derived_complexity_score_increases_with_large_changes() -> None:
    complexity, inputs = _derived_complexity_score(
        candidate_content={
            "prompt": "x" * 500,
            "tone": "urgent",
            "template": "A",
            "audience": "new-users",
        },
        baseline_content={"prompt": "baseline"},
        declared_complexity_score=0.0,
    )
    assert complexity > 0.08
    assert inputs["changed_fields"] >= 3
