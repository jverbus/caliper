# Worker / Scheduler Loop (P3-007)

P3-007 introduces a DB-backed worker loop for scheduled report generation and periodic policy-update triggers.

## What ships in this chunk

- `scheduled_tasks` table for durable due-task storage (`pending`/`running`/`completed` states).
- `WorkerLoop` orchestration (`apps/worker/loop.py`) that:
  - scans active jobs,
  - enqueues report tasks from `schedule_spec.report_cron` (v1 supports fixed `minute hour * * *` daily schedules),
  - enqueues policy-update tasks from `policy_spec.update_cadence.seconds`,
  - executes due tasks in due-time order.
- Worker entrypoint (`apps/worker/main.py`) with:
  - `--once` mode for one-shot run,
  - continuous polling mode (`--poll-seconds`, default 30).

## Task execution behavior

### Report tasks (`generate_report`)

- Loads job decisions/exposures/outcomes/guardrail events.
- Generates JSON + Markdown + HTML report payload via `ReportGenerator`.
- Persists report as latest report run.
- Appends `worker.report.generated` audit record.

### Policy-update tasks (`run_policy_update`)

- Builds a normalized reward dataset using `RewardEngine` from decisions/outcomes.
- Appends `worker.policy.updated` audit record with dataset size.

## Failure and recovery

- Due tasks are durable in `scheduled_tasks`.
- If task execution fails, task is requeued as `pending` for retry (+1 minute) and error text is captured in `last_error`.
- Restarting the worker continues from pending due tasks; no in-memory-only state is required.

## Test coverage

Integration tests in `tests/integration/test_worker_scheduler.py` validate:

- periodic report/policy task scheduling,
- due-task execution and report/audit persistence,
- restart recovery of pending due tasks.
