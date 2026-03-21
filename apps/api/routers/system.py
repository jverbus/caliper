from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from apps.api.decision_service import get_decision_summary
from apps.api.dependencies import get_engine, health_check, readiness_check, require_api_token

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return health_check()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return health_check()


@router.get("/readyz")
def readyz(engine: Annotated[Engine, Depends(get_engine)]) -> dict[str, str]:
    return readiness_check(engine)


@router.get("/v1/system/info", dependencies=[Depends(require_api_token)])
def system_info() -> dict[str, str]:
    return {"service": "caliper-api", "api_version": "v1"}


@router.get("/decision/summary")
def decision_summary(
    guardrail_regression: bool | None = None,
    guardrail_delta: float | None = None,
    max_guardrail_drop: float = 0.05,
    confidence: float | None = None,
    confidence_threshold: float = 0.0,
    policy_version: str = "v1",
) -> dict[str, str]:
    summary = get_decision_summary(
        guardrail_regression=guardrail_regression,
        guardrail_delta=guardrail_delta,
        max_guardrail_drop=max_guardrail_drop,
        confidence=confidence,
        confidence_threshold=confidence_threshold,
        policy_version=policy_version,
    )
    return summary.model_dump(mode="json")
