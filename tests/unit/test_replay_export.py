from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from caliper_core.models import (
    AssignResult,
    ExposureCreate,
    OutcomeCreate,
    OutcomeEvent,
    PolicyFamily,
)
from caliper_ope import ReplayExporter, summarize_dataset
from caliper_storage.engine import build_engine, init_db, make_session_factory
from caliper_storage.repositories import SQLRepository


def _timestamp(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def test_replay_export_contains_required_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.db"
    engine = build_engine(f"sqlite:///{db_path}")
    init_db(engine)
    repository = SQLRepository(make_session_factory(engine))

    decision = AssignResult(
        workspace_id="ws-replay",
        job_id="job-replay",
        unit_id="user-1",
        arm_id="arm-a",
        propensity=0.7,
        policy_family=PolicyFamily.FIXED_SPLIT,
        policy_version="v1",
        context={"country": "US", "plan": "pro"},
        timestamp=_timestamp("2026-03-14T20:00:00Z"),
        candidate_arms=["arm-a", "arm-b"],
    )
    repository.create_decision(decision)
    repository.create_exposure(
        ExposureCreate(
            workspace_id="ws-replay",
            job_id="job-replay",
            decision_id=decision.decision_id,
            unit_id="user-1",
            timestamp=_timestamp("2026-03-14T20:00:05Z"),
        )
    )
    repository.create_outcome(
        OutcomeCreate(
            workspace_id="ws-replay",
            job_id="job-replay",
            decision_id=decision.decision_id,
            unit_id="user-1",
            events=[
                OutcomeEvent(
                    outcome_type="conversion",
                    value=1.0,
                    timestamp=_timestamp("2026-03-14T20:03:00Z"),
                ),
                OutcomeEvent(
                    outcome_type="token_cost_usd",
                    value=-0.2,
                    timestamp=_timestamp("2026-03-14T20:03:10Z"),
                ),
            ],
        )
    )

    exporter = ReplayExporter(repository)
    rows = exporter.export(workspace_id="ws-replay", job_id="job-replay")

    assert len(rows) == 1
    row = rows[0]
    assert row.context == {"country": "US", "plan": "pro"}
    assert row.chosen_action == "arm-a"
    assert row.propensity == 0.7
    assert row.reward == 0.8
    assert _as_utc(row.assigned_at) == _timestamp("2026-03-14T20:00:00Z")
    assert row.first_exposed_at is not None
    assert row.latest_outcome_at is not None
    assert _as_utc(row.first_exposed_at) == _timestamp("2026-03-14T20:00:05Z")
    assert _as_utc(row.latest_outcome_at) == _timestamp("2026-03-14T20:03:10Z")

    summary = summarize_dataset(rows)
    assert summary.count == 1
    assert summary.average_reward == 0.8
