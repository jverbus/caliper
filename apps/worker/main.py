from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import time
from collections.abc import Callable
from typing import Any

from api.dependencies import get_session_factory
from worker.loop import WorkerLoop
from worker.scheduler_backends import TemporalSchedulerBackend

TemporalStarter = Callable[..., Any]


def _temporal_starter(target: str, namespace: str) -> TemporalStarter:
    def start(*, workflow: str, workflow_id: str, task_queue: str, payload: dict[str, Any]) -> str:
        async def _run() -> str:
            client_module = importlib.import_module("temporalio.client")
            client = await client_module.Client.connect(target, namespace=namespace)
            handle = await client.start_workflow(
                workflow,
                payload,
                id=workflow_id,
                task_queue=task_queue,
            )
            return str(handle.id)

        return asyncio.run(_run())

    return start


def main() -> None:
    parser = argparse.ArgumentParser(description="Caliper worker scheduler loop")
    parser.add_argument("--once", action="store_true", help="Run a single scheduler iteration")
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=30,
        help="Polling interval in seconds for continuous mode",
    )
    parser.add_argument(
        "--scheduler-backend",
        choices=["inline", "temporal"],
        default="inline",
        help="Task execution backend for due scheduler tasks",
    )
    parser.add_argument(
        "--temporal-target",
        default=os.getenv("CALIPER_TEMPORAL_TARGET", "localhost:7233"),
        help="Temporal host:port (used when --scheduler-backend=temporal)",
    )
    parser.add_argument(
        "--temporal-namespace",
        default=os.getenv("CALIPER_TEMPORAL_NAMESPACE", "default"),
        help="Temporal namespace (used when --scheduler-backend=temporal)",
    )
    parser.add_argument(
        "--temporal-task-queue",
        default=os.getenv("CALIPER_TEMPORAL_TASK_QUEUE", "caliper-scheduler"),
        help="Temporal task queue (used when --scheduler-backend=temporal)",
    )
    parser.add_argument(
        "--temporal-workflow",
        default=os.getenv("CALIPER_TEMPORAL_WORKFLOW", "caliper.scheduled_task"),
        help="Temporal workflow name (used when --scheduler-backend=temporal)",
    )
    args = parser.parse_args()

    scheduler_backend = None
    if args.scheduler_backend == "temporal":
        scheduler_backend = TemporalSchedulerBackend(
            workflow=args.temporal_workflow,
            task_queue=args.temporal_task_queue,
            starter=_temporal_starter(args.temporal_target, args.temporal_namespace),
        )

    loop = WorkerLoop(get_session_factory(), scheduler_backend=scheduler_backend)

    if args.once:
        loop.run_once()
        return

    while True:
        loop.run_once()
        time.sleep(max(1, args.poll_seconds))


if __name__ == "__main__":
    main()
