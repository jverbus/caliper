from __future__ import annotations

import argparse
import time

from api.dependencies import get_session_factory
from worker.loop import WorkerLoop


def main() -> None:
    parser = argparse.ArgumentParser(description="Caliper worker scheduler loop")
    parser.add_argument("--once", action="store_true", help="Run a single scheduler iteration")
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=30,
        help="Polling interval in seconds for continuous mode",
    )
    args = parser.parse_args()

    loop = WorkerLoop(get_session_factory())

    if args.once:
        loop.run_once()
        return

    while True:
        loop.run_once()
        time.sleep(max(1, args.poll_seconds))


if __name__ == "__main__":
    main()
