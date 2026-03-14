from __future__ import annotations

from datetime import UTC, datetime, timedelta

from caliper_core.events import EventEnvelope
from caliper_storage.engine import build_engine, init_db, make_session_factory
from caliper_storage.repositories import SQLiteRepository


def build_repo() -> SQLiteRepository:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return SQLiteRepository(make_session_factory(engine))


def test_event_ledger_append_and_replay_window_filters() -> None:
    repo = build_repo()
    now = datetime.now(tz=UTC)

    older = EventEnvelope(
        event_id="evt_old",
        workspace_id="ws-1",
        job_id="job-1",
        event_type="job.created",
        timestamp=now - timedelta(minutes=5),
        payload={"v": 1},
    )
    newer = EventEnvelope(
        event_id="evt_new",
        workspace_id="ws-1",
        job_id="job-1",
        event_type="job.updated",
        timestamp=now,
        payload={"v": 2},
    )

    repo.append(older)
    repo.append(newer)

    replayed = repo.replay(workspace_id="ws-1", job_id="job-1")
    assert [event.event_id for event in replayed] == ["evt_old", "evt_new"]

    recent_only = repo.replay(
        workspace_id="ws-1",
        job_id="job-1",
        start=now - timedelta(minutes=1),
    )
    assert [event.event_id for event in recent_only] == ["evt_new"]


def test_event_ledger_idempotent_append_returns_existing_event() -> None:
    repo = build_repo()

    first = EventEnvelope(
        event_id="evt_a",
        workspace_id="ws-1",
        job_id="job-1",
        event_type="decision.assigned",
        idempotency_key="idem-1",
        payload={"arm_id": "arm-a"},
    )
    duplicate = EventEnvelope(
        event_id="evt_b",
        workspace_id="ws-1",
        job_id="job-1",
        event_type="decision.assigned",
        idempotency_key="idem-1",
        payload={"arm_id": "arm-b"},
    )

    persisted_first = repo.append(first)
    persisted_duplicate = repo.append(duplicate)

    assert persisted_first.event_id == "evt_a"
    assert persisted_duplicate.event_id == "evt_a"

    replayed = repo.replay(workspace_id="ws-1", job_id="job-1")
    assert len(replayed) == 1
    assert replayed[0].payload["arm_id"] == "arm-a"
