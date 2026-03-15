from __future__ import annotations

from datetime import UTC, datetime

from caliper_core.events import EventEnvelope
from caliper_storage.clickhouse import ClickHouseAnalyticsStore


class FakeClickHouseClient:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.insert_calls: list[tuple[str, list[dict[str, object]]]] = []
        self.query_calls: list[tuple[str, dict[str, object]]] = []
        self.query_rows: list[dict[str, object]] = []

    def command(self, query: str) -> object:
        self.commands.append(query)
        return object()

    def insert(self, table: str, data: list[dict[str, object]]) -> object:
        self.insert_calls.append((table, data))
        return object()

    def query(self, query: str, parameters: dict[str, object]) -> list[dict[str, object]]:
        self.query_calls.append((query, parameters))
        return self.query_rows


def test_clickhouse_store_ensures_schema_and_appends_events() -> None:
    client = FakeClickHouseClient()
    store = ClickHouseAnalyticsStore(client=client)

    store.ensure_schema()

    assert len(client.commands) == 2
    assert "CREATE DATABASE IF NOT EXISTS caliper" in client.commands[0]
    assert "CREATE TABLE IF NOT EXISTS caliper.event_envelopes" in client.commands[1]

    event = EventEnvelope(
        event_id="evt_123",
        workspace_id="ws-demo",
        job_id="job-demo",
        event_type="decision.assigned",
        timestamp=datetime(2026, 3, 15, 8, 0, 0, tzinfo=UTC),
        payload={"arm_id": "arm-a", "propensity": 0.5},
    )

    persisted = store.append_event(event)

    assert persisted.event_id == "evt_123"
    assert len(client.insert_calls) == 1
    table, rows = client.insert_calls[0]
    assert table == "caliper.event_envelopes"
    assert rows[0]["workspace_id"] == "ws-demo"
    assert rows[0]["job_id"] == "job-demo"
    assert rows[0]["event_type"] == "decision.assigned"
    assert rows[0]["event_ts"] == datetime(2026, 3, 15, 8, 0, 0)
    assert rows[0]["payload_json"] == '{"arm_id": "arm-a", "propensity": 0.5}'


def test_clickhouse_store_summarizes_job_metrics() -> None:
    client = FakeClickHouseClient()
    client.query_rows = [
        {
            "event_count": 7,
            "distinct_event_types": 3,
            "first_event_at": "2026-03-14T23:00:00Z",
            "last_event_at": datetime(2026, 3, 15, 7, 50, 0),
        }
    ]
    store = ClickHouseAnalyticsStore(client=client)

    summary = store.summarize_job(workspace_id="ws-demo", job_id="job-demo")

    assert len(client.query_calls) == 1
    query, parameters = client.query_calls[0]
    assert "FROM caliper.event_envelopes" in query
    assert parameters == {"workspace_id": "ws-demo", "job_id": "job-demo"}

    assert summary.workspace_id == "ws-demo"
    assert summary.job_id == "job-demo"
    assert summary.event_count == 7
    assert summary.distinct_event_types == 3
    assert summary.first_event_at == datetime(2026, 3, 14, 23, 0, 0, tzinfo=UTC)
    assert summary.last_event_at == datetime(2026, 3, 15, 7, 50, 0, tzinfo=UTC)
