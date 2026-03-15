from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from caliper_core.events import EventEnvelope


class ClickHouseClient(Protocol):
    """Minimal ClickHouse client contract used by this backend seam."""

    def command(self, query: str) -> object: ...

    def insert(self, table: str, data: list[dict[str, Any]]) -> object: ...

    def query(self, query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class JobAnalyticsSummary:
    workspace_id: str
    job_id: str
    event_count: int
    distinct_event_types: int
    first_event_at: datetime | None
    last_event_at: datetime | None


class ClickHouseAnalyticsStore:
    """ClickHouse-backed analytics seam for event-heavy reporting workloads."""

    def __init__(
        self,
        *,
        client: ClickHouseClient,
        database: str = "caliper",
        table: str = "event_envelopes",
    ) -> None:
        self._client = client
        self._database = database
        self._table = table

    @property
    def qualified_table(self) -> str:
        return f"{self._database}.{self._table}"

    def ensure_schema(self) -> None:
        self._client.command(f"CREATE DATABASE IF NOT EXISTS {self._database}")
        self._client.command(
            f"""
            CREATE TABLE IF NOT EXISTS {self.qualified_table} (
                event_id String,
                workspace_id String,
                job_id String,
                event_type String,
                entity_id Nullable(String),
                idempotency_key Nullable(String),
                event_ts DateTime64(3, 'UTC'),
                payload_json String
            )
            ENGINE = MergeTree
            PARTITION BY toYYYYMM(event_ts)
            ORDER BY (workspace_id, job_id, event_ts, event_id)
            """.strip()
        )

    def append_event(self, event: EventEnvelope) -> EventEnvelope:
        self._client.insert(
            self.qualified_table,
            [
                {
                    "event_id": event.event_id,
                    "workspace_id": event.workspace_id,
                    "job_id": event.job_id,
                    "event_type": event.event_type,
                    "entity_id": event.entity_id,
                    "idempotency_key": event.idempotency_key,
                    "event_ts": event.timestamp.astimezone(UTC).replace(tzinfo=None),
                    "payload_json": json.dumps(event.payload, sort_keys=True),
                }
            ],
        )
        return event

    def summarize_job(self, *, workspace_id: str, job_id: str) -> JobAnalyticsSummary:
        rows = self._client.query(
            f"""
            SELECT
                count() AS event_count,
                countDistinct(event_type) AS distinct_event_types,
                min(event_ts) AS first_event_at,
                max(event_ts) AS last_event_at
            FROM {self.qualified_table}
            WHERE workspace_id = {{workspace_id:String}}
              AND job_id = {{job_id:String}}
            """.strip(),
            parameters={"workspace_id": workspace_id, "job_id": job_id},
        )
        row = rows[0] if rows else {}
        return JobAnalyticsSummary(
            workspace_id=workspace_id,
            job_id=job_id,
            event_count=int(row.get("event_count", 0) or 0),
            distinct_event_types=int(row.get("distinct_event_types", 0) or 0),
            first_event_at=_coerce_datetime(row.get("first_event_at")),
            last_event_at=_coerce_datetime(row.get("last_event_at")),
        )


def _coerce_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    msg = f"Unsupported datetime payload type: {type(value)!r}"
    raise TypeError(msg)
