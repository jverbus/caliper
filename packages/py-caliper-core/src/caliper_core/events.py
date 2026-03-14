from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

CANONICAL_EVENT_TYPES: tuple[str, ...] = (
    "job.created",
    "job.updated",
    "job.state_changed",
    "arm.registered",
    "arm.updated",
    "arm.state_changed",
    "decision.assigned",
    "decision.exposed",
    "outcome.observed",
    "guardrail.triggered",
    "policy.updated",
    "report.generated",
)


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    workspace_id: str
    job_id: str
    event_type: str
    entity_id: str | None = None
    idempotency_key: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    payload: dict[str, Any] = Field(default_factory=dict)


def is_canonical_event(event_type: str) -> bool:
    return event_type in CANONICAL_EVENT_TYPES
