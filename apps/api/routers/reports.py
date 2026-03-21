from __future__ import annotations

from typing import Annotated

from caliper_core.models import ReportGenerateRequest, ReportPayload
from caliper_sdk import CaliperService
from caliper_storage import SQLRepository
from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.dependencies import get_caliper_service, get_repository, require_api_token

router = APIRouter()


@router.post(
    "/v1/jobs/{job_id}/reports:generate",
    dependencies=[Depends(require_api_token)],
    response_model=ReportPayload,
)
def generate_report(
    job_id: str,
    payload: ReportGenerateRequest,
    service: Annotated[CaliperService, Depends(get_caliper_service)],
) -> ReportPayload:
    try:
        return service.generate_report(job_id=job_id, payload=payload)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if "not found" in detail:
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get(
    "/v1/jobs/{job_id}/reports/latest",
    dependencies=[Depends(require_api_token)],
    response_model=ReportPayload,
)
def get_latest_report(
    job_id: str,
    workspace_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> ReportPayload:
    report = repository.get_latest_report(workspace_id=workspace_id, job_id=job_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reports found for job '{job_id}'.",
        )
    return report
