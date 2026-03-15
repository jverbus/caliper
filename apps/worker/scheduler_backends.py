from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ScheduledTaskDispatch:
    task_id: int
    workspace_id: str
    job_id: str
    task_type: str


class SchedulerBackend(Protocol):
    """Dispatches due scheduled tasks to an execution backend."""

    def dispatch(self, task: ScheduledTaskDispatch) -> dict[str, Any]: ...


class TemporalWorkflowStarter(Protocol):
    """Protocol for a sync Temporal start-workflow adapter."""

    def __call__(
        self,
        *,
        workflow: str,
        workflow_id: str,
        task_queue: str,
        payload: dict[str, Any],
    ) -> Any: ...


@dataclass
class TemporalSchedulerBackend:
    """Dispatch due scheduler tasks as Temporal workflow executions."""

    workflow: str
    task_queue: str
    starter: TemporalWorkflowStarter

    def dispatch(self, task: ScheduledTaskDispatch) -> dict[str, Any]:
        workflow_id = self._workflow_id(task)
        payload = {
            "task_id": task.task_id,
            "workspace_id": task.workspace_id,
            "job_id": task.job_id,
            "task_type": task.task_type,
        }
        handle = self.starter(
            workflow=self.workflow,
            workflow_id=workflow_id,
            task_queue=self.task_queue,
            payload=payload,
        )
        return {
            "backend": "temporal",
            "workflow": self.workflow,
            "workflow_id": workflow_id,
            "task_queue": self.task_queue,
            "handle": str(handle) if handle is not None else None,
        }

    @staticmethod
    def _workflow_id(task: ScheduledTaskDispatch) -> str:
        return f"caliper-task-{task.workspace_id}-{task.job_id}-{task.task_type}-{task.task_id}"
