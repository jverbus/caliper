from __future__ import annotations

from typing import Annotated

from caliper_core.models import ReportGenerateRequest, ReportPayload
from caliper_reports import ReportGenerator
from caliper_storage import SQLRepository
from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.dependencies import get_repository, require_api_token

router = APIRouter()


@router.post(
    "/v1/jobs/{job_id}/reports:generate",
    dependencies=[Depends(require_api_token)],
    response_model=ReportPayload,
)
def generate_report(
    job_id: str,
    payload: ReportGenerateRequest,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> ReportPayload:
    job = repository.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    if payload.workspace_id != job.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workspace_id does not match the job workspace.",
        )

    generator = ReportGenerator()
    report = generator.generate(
        job=job,
        arms=repository.list_arms(workspace_id=payload.workspace_id, job_id=job_id),
        decisions=repository.list_decisions(workspace_id=payload.workspace_id, job_id=job_id),
        exposures=repository.list_exposures(workspace_id=payload.workspace_id, job_id=job_id),
        outcomes=repository.list_outcomes(workspace_id=payload.workspace_id, job_id=job_id),
        guardrails=repository.list_guardrail_events(
            workspace_id=payload.workspace_id,
            job_id=job_id,
        ),
    )
    repository.save_report(report)
    repository.append_audit(
        workspace_id=payload.workspace_id,
        job_id=job_id,
        action="report.generated",
        metadata={"report_id": report.report_id},
    )
    return report


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
