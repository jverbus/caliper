# Temporal Scheduler Backend (PV1-007)

PV1-007 adds a Temporal-backed scheduler execution backend for Caliper worker due-tasks.

## What ships in this chunk

- New scheduler backend abstractions in `apps/worker/scheduler_backends.py`:
  - `SchedulerBackend` dispatch protocol.
  - `ScheduledTaskDispatch` payload contract.
  - `TemporalSchedulerBackend` that maps due tasks to Temporal workflow starts.
- Worker loop integration (`apps/worker/loop.py`):
  - optional `scheduler_backend` injection,
  - due tasks can be dispatched externally instead of executed inline,
  - dispatched tasks append `worker.task.dispatched` audit records.
- Worker CLI/runtime options (`apps/worker/main.py`) for Temporal mode:
  - `--scheduler-backend temporal`
  - `--temporal-target`
  - `--temporal-namespace`
  - `--temporal-task-queue`
  - `--temporal-workflow`

## Dispatch contract

Temporal dispatch sends one workflow execution per due task with payload:

```json
{
  "task_id": "...",
  "workspace_id": "...",
  "job_id": "...",
  "task_type": "generate_report | run_policy_update"
}
```

Workflow IDs are deterministic:

`caliper-task-<workspace_id>-<job_id>-<task_type>-<task_id>`

## Runtime notes

- Default behavior remains inline execution (`--scheduler-backend inline`).
- Temporal mode requires `temporalio` at runtime; worker imports it lazily only when Temporal mode is selected.
- Temporal mode is intended for distributed execution where dedicated Temporal workers perform the task body.

## Test coverage

- `tests/unit/test_temporal_scheduler_backend.py` validates workflow ID/payload/metadata shaping.
- `tests/integration/test_worker_scheduler.py::test_worker_dispatches_due_tasks_to_scheduler_backend` validates due-task dispatch and audit emission via backend injection.
