from __future__ import annotations

import pytest
from caliper_core.models import (
    AssignResult,
    ExposureCreate,
    ExposureType,
    GuardrailAction,
    JobCreate,
    PolicyFamily,
)
from pydantic import ValidationError


def _job_payload() -> dict[str, object]:
    return {
        "workspace_id": "ws_demo",
        "name": "landing-page-signup-test",
        "surface_type": "web",
        "objective_spec": {"reward_formula": "1.0 * signup"},
        "guardrail_spec": {
            "rules": [
                {
                    "metric": "error_rate",
                    "op": "<",
                    "threshold": 0.01,
                    "action": "pause",
                }
            ]
        },
        "policy_spec": {
            "policy_family": "fixed_split",
            "params": {"weights": {"arm_a": 0.5, "arm_b": 0.5}},
            "update_cadence": {"mode": "periodic", "seconds": 300},
        },
    }


def test_job_create_requires_expected_fields() -> None:
    with pytest.raises(ValidationError):
        JobCreate.model_validate({"workspace_id": "ws_demo"})


def test_job_create_parses_enum_values() -> None:
    model = JobCreate.model_validate(_job_payload())
    assert model.policy_spec.policy_family is PolicyFamily.FIXED_SPLIT
    assert model.guardrail_spec.rules[0].action is GuardrailAction.PAUSE


def test_assign_result_rejects_invalid_propensity() -> None:
    with pytest.raises(ValidationError):
        AssignResult.model_validate(
            {
                "workspace_id": "ws_demo",
                "job_id": "job_1",
                "unit_id": "visitor_1",
                "arm_id": "arm_a",
                "propensity": 0,
                "policy_family": "fixed_split",
                "policy_version": "2026-03-14.1",
            }
        )


def test_exposure_type_uses_enum() -> None:
    model = ExposureCreate.model_validate(
        {
            "workspace_id": "ws_demo",
            "job_id": "job_1",
            "decision_id": "dec_1",
            "unit_id": "unit_1",
            "exposure_type": "executed",
        }
    )
    assert model.exposure_type is ExposureType.EXECUTED
