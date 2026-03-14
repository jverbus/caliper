from __future__ import annotations

from datetime import UTC, datetime

from caliper_core.models import GuardrailAction, GuardrailRule, GuardrailSpec
from caliper_reward.engine import RewardRecord
from caliper_reward.guardrails import GuardrailEngine


def _record(*, arm_id: str, error_rate: float) -> RewardRecord:
    return RewardRecord(
        workspace_id="ws",
        job_id="job",
        decision_id=f"dec-{arm_id}",
        unit_id=f"unit-{arm_id}",
        arm_id=arm_id,
        propensity=0.5,
        reward=1.0,
        normalized_reward=1.0,
        observed_at=datetime(2026, 3, 14, tzinfo=UTC),
        metrics={"error_rate": error_rate},
    )


def test_guardrail_engine_emits_pause_breach_event() -> None:
    engine = GuardrailEngine()
    evaluations = engine.evaluate(
        workspace_id="ws",
        job_id="job",
        guardrail_spec=GuardrailSpec(
            rules=[
                GuardrailRule(
                    metric="error_rate",
                    op=">",
                    threshold=0.2,
                    action=GuardrailAction.PAUSE,
                )
            ]
        ),
        records=[_record(arm_id="arm-a", error_rate=0.3)],
    )

    assert len(evaluations) == 1
    assert evaluations[0].event.action == GuardrailAction.PAUSE
    assert evaluations[0].event.metric == "error_rate"
    assert evaluations[0].event.metadata["observed"] == 0.3


def test_guardrail_engine_targets_worst_arm_for_demote_actions() -> None:
    engine = GuardrailEngine()
    evaluations = engine.evaluate(
        workspace_id="ws",
        job_id="job",
        guardrail_spec=GuardrailSpec(
            rules=[
                GuardrailRule(
                    metric="error_rate",
                    op=">=",
                    threshold=0.2,
                    action=GuardrailAction.DEMOTE,
                )
            ]
        ),
        records=[
            _record(arm_id="arm-a", error_rate=0.1),
            _record(arm_id="arm-b", error_rate=0.4),
        ],
    )

    assert len(evaluations) == 1
    assert evaluations[0].target_arm_id == "arm-b"
