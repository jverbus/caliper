from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from examples.email_demo.demo import run_demo as run_email_demo
from examples.web_demo.demo import run_demo as run_web_demo
from examples.workflow_demo.demo import run_demo as run_workflow_demo

RunDemoFn = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class DemoSurface:
    name: str
    runner: RunDemoFn


SURFACES: tuple[DemoSurface, ...] = (
    DemoSurface(name="workflow", runner=run_workflow_demo),
    DemoSurface(name="web", runner=run_web_demo),
    DemoSurface(name="email", runner=run_email_demo),
)


def _write_report_bundle(*, report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(report["markdown"], encoding="utf-8")
    (output_dir / "report.html").write_text(report["html"], encoding="utf-8")


def seed_embedded_demo_data(*, db_dir: Path, report_dir: Path) -> list[dict[str, str]]:
    db_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, str]] = []
    for surface in SURFACES:
        db_url = f"sqlite:///{(db_dir / f'{surface.name}-demo.db').as_posix()}"
        report = surface.runner(
            mode="embedded",
            db_url=db_url,
            api_url="http://127.0.0.1:8000",
            api_token=None,
        )
        output_dir = report_dir / surface.name
        _write_report_bundle(report=report, output_dir=output_dir)
        summary.append(
            {
                "surface": surface.name,
                "db_url": db_url,
                "report_id": str(report.get("report_id", "")),
                "artifacts": str(output_dir),
            }
        )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed deterministic Caliper demo data")
    parser.add_argument(
        "--db-dir",
        default="data/seed",
        help="Directory for seeded SQLite demo DB files",
    )
    parser.add_argument(
        "--report-dir",
        default="reports/seed",
        help="Directory for seeded demo report artifacts",
    )
    parser.add_argument(
        "--summary-file",
        default="reports/seed/manifest.json",
        help="Path for machine-readable seed summary manifest",
    )
    args = parser.parse_args()

    db_dir = Path(args.db_dir)
    report_dir = Path(args.report_dir)
    summary = seed_embedded_demo_data(db_dir=db_dir, report_dir=report_dir)

    summary_file = Path(args.summary_file)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("seeded demo data")
    for row in summary:
        print(f"- {row['surface']}: {row['report_id']} -> {row['artifacts']}")
    print(f"manifest={summary_file}")


if __name__ == "__main__":
    main()
