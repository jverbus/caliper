from __future__ import annotations

import json
from typing import Annotated

from caliper_core.models import (
    AutotuneCandidate,
    AutotuneCandidateCreate,
    AutotunePromotion,
    AutotuneResult,
    AutotuneRun,
    AutotuneRunCreate,
)
from caliper_storage import SQLRepository
from fastapi import APIRouter, Depends, HTTPException

from apps.api.autotune_evaluator import FrozenEvaluatorConfig, evaluate_fixed_score
from apps.api.dependencies import get_repository, require_api_token
from apps.api.services.autotune import (
    autotune_diff_summary,
    autotune_disposition,
    derived_complexity_score,
    run_promotion_replay_check,
    serialize_promotion_diff,
    to_candidate_config,
    validate_autotune_confirmation,
    validate_autotune_editable_surface,
)

router = APIRouter()


@router.post(
    "/v1/autotune/candidates",
    dependencies=[Depends(require_api_token)],
    response_model=AutotuneCandidate,
)
def autotune_candidate_create(
    payload: AutotuneCandidateCreate,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> AutotuneCandidate:
    editable_surface = validate_autotune_editable_surface(payload.editable_surface)
    candidate_payload = payload.model_dump()
    candidate_payload["editable_surface"] = editable_surface
    candidate = repository.create_autotune_candidate(AutotuneCandidate(**candidate_payload))
    return candidate


@router.get(
    "/v1/autotune/candidates",
    dependencies=[Depends(require_api_token)],
    response_model=list[AutotuneCandidate],
)
def autotune_candidate_list(
    experiment_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> list[AutotuneCandidate]:
    return repository.list_autotune_candidates(experiment_id=experiment_id)


@router.post(
    "/v1/autotune/runs",
    dependencies=[Depends(require_api_token)],
    response_model=AutotuneRun,
)
def autotune_run(
    payload: AutotuneRunCreate,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> AutotuneRun:
    candidate = repository.get_autotune_candidate(candidate_id=payload.candidate_id)
    baseline = repository.get_autotune_candidate(candidate_id=payload.baseline_candidate_id)
    if candidate is None or baseline is None:
        raise HTTPException(status_code=404, detail="Candidate or baseline candidate not found")

    frozen = FrozenEvaluatorConfig(
        seed=payload.seed,
        synthetic_user_budget=payload.budget,
        **payload.simulation_config_snapshot,
    )
    candidate_complexity_score, complexity_inputs = derived_complexity_score(
        candidate_content=candidate.content,
        baseline_content=baseline.content,
        declared_complexity_score=candidate.complexity_score,
    )

    baseline_eval = evaluate_fixed_score(
        candidate=to_candidate_config(baseline),
        frozen_config=frozen,
    )
    eval_result = evaluate_fixed_score(
        candidate=to_candidate_config(candidate, complexity_score=candidate_complexity_score),
        frozen_config=frozen,
    )

    candidate_score = eval_result.score
    baseline_score = baseline_eval.score
    delta_vs_baseline = candidate_score - baseline_score
    complexity_penalty = eval_result.score_breakdown.get("complexity_penalty", 0.0)
    keep_discard, disposition_reason = autotune_disposition(
        candidate_score=candidate_score,
        baseline_score=baseline_score,
        complexity_penalty=complexity_penalty,
        hard_fail_code=eval_result.hard_fail_code,
    )

    run = repository.create_autotune_run(AutotuneRun(**payload.model_dump()))
    repository.save_autotune_result(
        AutotuneResult(
            run_id=run.run_id,
            candidate_id=run.candidate_id,
            score=candidate_score,
            score_breakdown={
                **eval_result.score_breakdown,
                "candidate_score": candidate_score,
                "baseline_score": baseline_score,
                "delta_vs_baseline": delta_vs_baseline,
                **complexity_inputs,
            },
            decision_summary_snapshot={
                "recommendation": eval_result.recommendation,
            },
            analytics_snapshot=eval_result.analytics_snapshot.model_dump(mode="json"),
            keep_discard=keep_discard,
            reason=disposition_reason,
            hard_fail_code=eval_result.hard_fail_code,
        )
    )
    return run


@router.get(
    "/v1/autotune/runs/{run_id}/status",
    dependencies=[Depends(require_api_token)],
)
def autotune_status(
    run_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> dict[str, str]:
    run = repository.get_autotune_run(run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {"run_id": run_id, "status": run.status}


@router.get(
    "/v1/autotune/runs/{run_id}/result",
    dependencies=[Depends(require_api_token)],
    response_model=AutotuneResult,
)
def autotune_result_get(
    run_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> AutotuneResult:
    result = repository.get_autotune_result(run_id=run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for run '{run_id}' not found")
    return result


@router.post(
    "/v1/autotune/runs/{run_id}/keep",
    dependencies=[Depends(require_api_token)],
    response_model=AutotuneResult,
)
def autotune_keep(
    run_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
    reason: str | None = None,
) -> AutotuneResult:
    result = repository.set_autotune_result_disposition(
        run_id=run_id,
        disposition="keep",
        reason=reason,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for run '{run_id}' not found")
    return result


@router.post(
    "/v1/autotune/runs/{run_id}/discard",
    dependencies=[Depends(require_api_token)],
    response_model=AutotuneResult,
)
def autotune_discard(
    run_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
    reason: str | None = None,
) -> AutotuneResult:
    result = repository.set_autotune_result_disposition(
        run_id=run_id,
        disposition="discard",
        reason=reason,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for run '{run_id}' not found")
    return result


@router.post(
    "/v1/autotune/promote",
    dependencies=[Depends(require_api_token)],
    response_model=AutotunePromotion,
)
def autotune_promote(
    payload: AutotunePromotion,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> AutotunePromotion:
    validate_autotune_confirmation(payload.confirmation)

    run = repository.get_autotune_run(run_id=payload.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{payload.run_id}' not found")
    result = repository.get_autotune_result(run_id=payload.run_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Result for run '{payload.run_id}' not found",
        )
    candidate = repository.get_autotune_candidate(candidate_id=payload.candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate '{payload.candidate_id}' not found",
        )
    if run.candidate_id != payload.candidate_id:
        raise HTTPException(
            status_code=400,
            detail="candidate_id must match run.candidate_id for promotion",
        )
    baseline = repository.get_autotune_candidate(candidate_id=run.baseline_candidate_id)
    if baseline is None:
        raise HTTPException(
            status_code=404,
            detail=f"Baseline candidate '{run.baseline_candidate_id}' not found",
        )

    replay_check = run_promotion_replay_check(
        candidate=candidate,
        baseline=baseline,
        run=run,
        result=result,
    )
    if not replay_check["passed"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "pre-promotion replay check failed",
                "replay_check": replay_check,
            },
        )

    promotion_diff_summary = payload.diff_summary or autotune_diff_summary(
        candidate=candidate,
        baseline=baseline,
        result=result,
    )
    promotion = payload.model_copy(
        update={
            "target_surface": validate_autotune_editable_surface(payload.target_surface),
            "diff_summary": serialize_promotion_diff(
                summary=promotion_diff_summary,
                run_id=payload.run_id,
                promoted_content=candidate.content,
                replay_check=replay_check,
            ),
            "promoted_content": candidate.content,
            "replay_check": replay_check,
        }
    )
    return repository.create_autotune_promotion(promotion)


@router.get("/v1/autotune/export.jsonl", dependencies=[Depends(require_api_token)])
def autotune_export_jsonl(
    experiment_id: str,
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> dict[str, str]:
    rows = [
        result.model_dump(mode="json")
        for result in repository.list_autotune_results(experiment_id=experiment_id)
    ]
    return {
        "experiment_id": experiment_id,
        "jsonl": "\n".join(json.dumps(row, sort_keys=True, default=str) for row in rows),
    }
