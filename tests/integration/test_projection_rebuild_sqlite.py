from __future__ import annotations

from caliper_core.events import EventEnvelope
from caliper_events.projections import rebuild_job_projections
from caliper_storage.engine import build_engine, init_db, make_session_factory
from caliper_storage.repositories import SQLiteRepository


def build_repo() -> SQLiteRepository:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return SQLiteRepository(make_session_factory(engine))


def test_projection_rebuild_writes_aggregate_metrics_and_audit_record() -> None:
    repo = build_repo()

    events = [
        EventEnvelope(
            workspace_id="ws-1",
            job_id="job-1",
            event_type="decision.assigned",
            payload={"arm_id": "arm-a"},
        ),
        EventEnvelope(
            workspace_id="ws-1",
            job_id="job-1",
            event_type="decision.exposed",
            payload={"arm_id": "arm-a"},
        ),
        EventEnvelope(
            workspace_id="ws-1",
            job_id="job-1",
            event_type="decision.assigned",
            payload={"arm_id": "arm-b"},
        ),
        EventEnvelope(
            workspace_id="ws-1",
            job_id="job-1",
            event_type="outcome.observed",
            payload={"arm_id": "arm-b"},
        ),
    ]

    for event in events:
        repo.append(event)

    result = rebuild_job_projections(repository=repo, workspace_id="ws-1", job_id="job-1")

    assert result.event_count == 4
    assert result.rebuild_id is not None
    assert result.by_arm["arm-a"].assignments == 1
    assert result.by_arm["arm-a"].exposures == 1
    assert result.by_arm["arm-a"].outcomes == 0
    assert result.by_arm["arm-b"].assignments == 1
    assert result.by_arm["arm-b"].exposures == 0
    assert result.by_arm["arm-b"].outcomes == 1

    metrics_rows = repo.list_projection_metrics(workspace_id="ws-1", job_id="job-1")
    assert [(row.arm_id, row.assignments, row.exposures, row.outcomes) for row in metrics_rows] == [
        ("arm-a", 1, 1, 0),
        ("arm-b", 1, 0, 1),
    ]

    audit_rows = repo.list_projection_rebuild_audits(workspace_id="ws-1", job_id="job-1")
    assert len(audit_rows) == 1
    assert audit_rows[0].event_count == 4


def test_projection_rebuild_replaces_prior_aggregate_state() -> None:
    repo = build_repo()

    repo.append(
        EventEnvelope(
            workspace_id="ws-1",
            job_id="job-1",
            event_type="decision.assigned",
            payload={"arm_id": "arm-a"},
        )
    )
    rebuild_job_projections(repository=repo, workspace_id="ws-1", job_id="job-1")

    repo.append(
        EventEnvelope(
            workspace_id="ws-1",
            job_id="job-1",
            event_type="decision.assigned",
            payload={"arm_id": "arm-b"},
        )
    )
    rebuild_job_projections(repository=repo, workspace_id="ws-1", job_id="job-1")

    metrics_rows = repo.list_projection_metrics(workspace_id="ws-1", job_id="job-1")
    assert [(row.arm_id, row.assignments) for row in metrics_rows] == [
        ("arm-a", 1),
        ("arm-b", 1),
    ]

    audit_rows = repo.list_projection_rebuild_audits(workspace_id="ws-1", job_id="job-1")
    assert len(audit_rows) == 2
    assert audit_rows[0].event_count == 2
    assert audit_rows[1].event_count == 1
