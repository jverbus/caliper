from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from caliper_core.events import EventEnvelope
from caliper_storage.repositories import SQLRepository


@dataclass
class ProjectionCounts:
    assignments: int = 0
    exposures: int = 0
    outcomes: int = 0


@dataclass
class ProjectionRebuildResult:
    workspace_id: str
    job_id: str
    event_count: int
    by_arm: dict[str, ProjectionCounts] = field(default_factory=dict)
    rebuild_id: str | None = None


def _arm_id_for_event(event: EventEnvelope) -> str | None:
    payload_arm_id = event.payload.get("arm_id")
    if isinstance(payload_arm_id, str) and payload_arm_id:
        return payload_arm_id

    if event.entity_id is not None and event.entity_id.startswith("arm_"):
        return event.entity_id

    return None


def rebuild_job_projections(
    *,
    repository: SQLRepository,
    workspace_id: str,
    job_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ProjectionRebuildResult:
    events = repository.replay(workspace_id=workspace_id, job_id=job_id, start=start, end=end)

    counts_by_arm: dict[str, ProjectionCounts] = {}

    for event in events:
        arm_id = _arm_id_for_event(event)
        if arm_id is None:
            continue

        bucket = counts_by_arm.setdefault(arm_id, ProjectionCounts())

        if event.event_type == "decision.assigned":
            bucket.assignments += 1
        elif event.event_type == "decision.exposed":
            bucket.exposures += 1
        elif event.event_type == "outcome.observed":
            bucket.outcomes += 1

    repository.replace_projection_metrics(
        workspace_id=workspace_id,
        job_id=job_id,
        metrics={
            arm_id: {
                "assignments": counts.assignments,
                "exposures": counts.exposures,
                "outcomes": counts.outcomes,
            }
            for arm_id, counts in counts_by_arm.items()
        },
    )

    rebuild_id = repository.record_projection_rebuild(
        workspace_id=workspace_id,
        job_id=job_id,
        event_count=len(events),
        start=start,
        end=end,
    )

    return ProjectionRebuildResult(
        workspace_id=workspace_id,
        job_id=job_id,
        event_count=len(events),
        by_arm=counts_by_arm,
        rebuild_id=rebuild_id,
    )
