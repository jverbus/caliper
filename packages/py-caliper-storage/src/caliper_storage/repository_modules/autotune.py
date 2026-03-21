from __future__ import annotations

from caliper_core.models import AutotuneCandidate, AutotunePromotion, AutotuneResult, AutotuneRun
from sqlalchemy import select

from caliper_storage.repository_modules.base import SQLRepositoryBase
from caliper_storage.sqlalchemy_models import (
    AutotuneCandidateRow,
    AutotunePromotionRow,
    AutotuneResultRow,
    AutotuneRunRow,
)


class AutotuneRepositoryMixin(SQLRepositoryBase):
    def create_autotune_candidate(self, candidate: AutotuneCandidate) -> AutotuneCandidate:
        with self._session() as session:
            session.add(
                AutotuneCandidateRow(
                    candidate_id=candidate.candidate_id,
                    experiment_id=candidate.experiment_id,
                    candidate_type=candidate.candidate_type,
                    parent_candidate_id=candidate.parent_candidate_id,
                    editable_surface=candidate.editable_surface,
                    content_json=candidate.content,
                    complexity_score=candidate.complexity_score,
                    created_at=candidate.created_at,
                )
            )
        return candidate

    def list_autotune_candidates(self, *, experiment_id: str) -> list[AutotuneCandidate]:
        statement = (
            select(AutotuneCandidateRow)
            .where(AutotuneCandidateRow.experiment_id == experiment_id)
            .order_by(AutotuneCandidateRow.created_at.asc())
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [
                AutotuneCandidate.model_validate(
                    {
                        "candidate_id": row.candidate_id,
                        "experiment_id": row.experiment_id,
                        "candidate_type": row.candidate_type,
                        "parent_candidate_id": row.parent_candidate_id,
                        "editable_surface": row.editable_surface,
                        "content": row.content_json,
                        "complexity_score": row.complexity_score,
                        "created_at": row.created_at,
                    }
                )
                for row in rows
            ]

    def get_autotune_candidate(self, *, candidate_id: str) -> AutotuneCandidate | None:
        with self._session() as session:
            row = session.get(AutotuneCandidateRow, candidate_id)
            if row is None:
                return None
            return AutotuneCandidate.model_validate(
                {
                    "candidate_id": row.candidate_id,
                    "experiment_id": row.experiment_id,
                    "candidate_type": row.candidate_type,
                    "parent_candidate_id": row.parent_candidate_id,
                    "editable_surface": row.editable_surface,
                    "content": row.content_json,
                    "complexity_score": row.complexity_score,
                    "created_at": row.created_at,
                }
            )

    def create_autotune_run(self, run: AutotuneRun) -> AutotuneRun:
        with self._session() as session:
            session.add(
                AutotuneRunRow(
                    run_id=run.run_id,
                    experiment_id=run.experiment_id,
                    candidate_id=run.candidate_id,
                    baseline_candidate_id=run.baseline_candidate_id,
                    simulation_config_snapshot_json=run.simulation_config_snapshot,
                    seed=run.seed,
                    budget=run.budget,
                    status=run.status,
                    evaluator_version=run.evaluator_version,
                    started_at=run.started_at,
                    ended_at=run.ended_at,
                )
            )
        return run

    def get_autotune_run(self, *, run_id: str) -> AutotuneRun | None:
        with self._session() as session:
            row = session.get(AutotuneRunRow, run_id)
            if row is None:
                return None
            return AutotuneRun.model_validate(
                {
                    "run_id": row.run_id,
                    "experiment_id": row.experiment_id,
                    "candidate_id": row.candidate_id,
                    "baseline_candidate_id": row.baseline_candidate_id,
                    "simulation_config_snapshot": row.simulation_config_snapshot_json,
                    "seed": row.seed,
                    "budget": row.budget,
                    "status": row.status,
                    "evaluator_version": row.evaluator_version,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                }
            )

    def save_autotune_result(self, result: AutotuneResult) -> AutotuneResult:
        with self._session() as session:
            session.add(
                AutotuneResultRow(
                    result_id=result.result_id,
                    run_id=result.run_id,
                    candidate_id=result.candidate_id,
                    score=result.score,
                    score_breakdown_json=result.score_breakdown,
                    decision_summary_snapshot_json=result.decision_summary_snapshot,
                    analytics_snapshot_json=result.analytics_snapshot,
                    keep_discard=result.keep_discard,
                    reason=result.reason,
                    hard_fail_code=result.hard_fail_code,
                    created_at=result.created_at,
                )
            )
        return result

    def get_autotune_result(self, *, run_id: str) -> AutotuneResult | None:
        statement = select(AutotuneResultRow).where(AutotuneResultRow.run_id == run_id)
        with self._session() as session:
            row = session.scalars(statement).first()
            if row is None:
                return None
            return AutotuneResult.model_validate(
                {
                    "result_id": row.result_id,
                    "run_id": row.run_id,
                    "candidate_id": row.candidate_id,
                    "score": row.score,
                    "score_breakdown": row.score_breakdown_json,
                    "decision_summary_snapshot": row.decision_summary_snapshot_json,
                    "analytics_snapshot": row.analytics_snapshot_json,
                    "keep_discard": row.keep_discard,
                    "reason": row.reason,
                    "hard_fail_code": row.hard_fail_code,
                    "created_at": row.created_at,
                }
            )

    def set_autotune_result_disposition(
        self, *, run_id: str, disposition: str, reason: str | None = None
    ) -> AutotuneResult | None:
        statement = select(AutotuneResultRow).where(AutotuneResultRow.run_id == run_id)
        with self._session() as session:
            row = session.scalars(statement).first()
            if row is None:
                return None
            row.keep_discard = disposition
            row.reason = reason
            session.add(row)
            session.flush()
            return AutotuneResult.model_validate(
                {
                    "result_id": row.result_id,
                    "run_id": row.run_id,
                    "candidate_id": row.candidate_id,
                    "score": row.score,
                    "score_breakdown": row.score_breakdown_json,
                    "decision_summary_snapshot": row.decision_summary_snapshot_json,
                    "analytics_snapshot": row.analytics_snapshot_json,
                    "keep_discard": row.keep_discard,
                    "reason": row.reason,
                    "hard_fail_code": row.hard_fail_code,
                    "created_at": row.created_at,
                }
            )

    def create_autotune_promotion(self, promotion: AutotunePromotion) -> AutotunePromotion:
        with self._session() as session:
            session.add(
                AutotunePromotionRow(
                    promotion_id=promotion.promotion_id,
                    candidate_id=promotion.candidate_id,
                    promoted_by=promotion.promoted_by,
                    target_surface=promotion.target_surface,
                    confirmation=promotion.confirmation,
                    diff_summary=promotion.diff_summary,
                    created_at=promotion.created_at,
                )
            )
        return promotion

    def list_autotune_results(self, *, experiment_id: str) -> list[AutotuneResult]:
        statement = (
            select(AutotuneResultRow)
            .join(AutotuneRunRow, AutotuneRunRow.run_id == AutotuneResultRow.run_id)
            .where(AutotuneRunRow.experiment_id == experiment_id)
            .order_by(AutotuneResultRow.created_at.asc())
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
            return [
                AutotuneResult.model_validate(
                    {
                        "result_id": row.result_id,
                        "run_id": row.run_id,
                        "candidate_id": row.candidate_id,
                        "score": row.score,
                        "score_breakdown": row.score_breakdown_json,
                        "decision_summary_snapshot": row.decision_summary_snapshot_json,
                        "analytics_snapshot": row.analytics_snapshot_json,
                        "keep_discard": row.keep_discard,
                        "reason": row.reason,
                        "hard_fail_code": row.hard_fail_code,
                        "created_at": row.created_at,
                    }
                )
                for row in rows
            ]
