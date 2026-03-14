from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from caliper_core.models import (
    Arm,
    AssignRequest,
    AssignResult,
    ExposureCreate,
    GuardrailEvent,
    Job,
    JobCreate,
    JobCreateResponse,
    JobPatch,
    OutcomeCreate,
    PolicySnapshot,
)

DOMAIN_MODELS: dict[str, type[BaseModel]] = {
    "job_create": JobCreate,
    "job": Job,
    "job_patch": JobPatch,
    "job_create_response": JobCreateResponse,
    "arm": Arm,
    "assign_request": AssignRequest,
    "assign_result": AssignResult,
    "exposure_create": ExposureCreate,
    "outcome_create": OutcomeCreate,
    "guardrail_event": GuardrailEvent,
    "policy_snapshot": PolicySnapshot,
}


def generate_json_schemas() -> dict[str, dict[str, Any]]:
    return {name: model.model_json_schema() for name, model in DOMAIN_MODELS.items()}
