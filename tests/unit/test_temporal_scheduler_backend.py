from __future__ import annotations

from worker.scheduler_backends import ScheduledTaskDispatch, TemporalSchedulerBackend


def test_temporal_scheduler_backend_dispatch_shapes_workflow_payload() -> None:
    calls: list[dict[str, object]] = []

    def starter(
        *,
        workflow: str,
        workflow_id: str,
        task_queue: str,
        payload: dict[str, object],
    ) -> str:
        calls.append(
            {
                "workflow": workflow,
                "workflow_id": workflow_id,
                "task_queue": task_queue,
                "payload": payload,
            }
        )
        return "handle-123"

    backend = TemporalSchedulerBackend(
        workflow="caliper.scheduled_task",
        task_queue="caliper-scheduler",
        starter=starter,
    )

    metadata = backend.dispatch(
        ScheduledTaskDispatch(
            task_id=1,
            workspace_id="ws-1",
            job_id="job-1",
            task_type="generate_report",
        )
    )

    assert len(calls) == 1
    assert calls[0]["workflow"] == "caliper.scheduled_task"
    assert calls[0]["task_queue"] == "caliper-scheduler"
    assert calls[0]["workflow_id"] == "caliper-task-ws-1-job-1-generate_report-1"
    assert calls[0]["payload"] == {
        "task_id": 1,
        "workspace_id": "ws-1",
        "job_id": "job-1",
        "task_type": "generate_report",
    }

    assert metadata["backend"] == "temporal"
    assert metadata["workflow"] == "caliper.scheduled_task"
    assert metadata["task_queue"] == "caliper-scheduler"
    assert metadata["handle"] == "handle-123"
