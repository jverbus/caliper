from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from caliper_adapters import WebAdapter
from caliper_core.models import (
    ArmBulkRegisterRequest,
    ArmInput,
    ArmType,
    GuardrailSpec,
    Job,
    ObjectiveSpec,
    PolicyFamily,
    PolicySpec,
    ReportGenerateRequest,
    SegmentSpec,
    SurfaceType,
)
from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient

type DemoClient = EmbeddedCaliperClient | ServiceCaliperClient


def _sqlite_db_path(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None

    sqlite_path = db_url.removeprefix("sqlite:///")
    if not sqlite_path or sqlite_path == ":memory:":
        return None

    db_file = Path(sqlite_path)
    if not db_file.is_absolute():
        db_file = Path.cwd() / db_file
    return db_file


def _ensure_sqlite_parent_dir(db_url: str) -> None:
    db_file = _sqlite_db_path(db_url)
    if db_file is None:
        return
    db_file.parent.mkdir(parents=True, exist_ok=True)


def _reset_sqlite_file(db_url: str) -> None:
    db_file = _sqlite_db_path(db_url)
    if db_file is None:
        return
    if db_file.exists():
        db_file.unlink()


def _build_demo_job(*, workspace_id: str, name: str) -> Job:
    return Job(
        workspace_id=workspace_id,
        name=name,
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(
            reward_formula="(0.30 * click) + conversion",
            penalties=[],
            secondary_metrics=["click", "conversion"],
        ),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.THOMPSON_SAMPLING,
            params={
                "arms": {
                    "landing-a": {"successes": 16, "failures": 20},
                    "landing-b": {"successes": 24, "failures": 16},
                },
                "seed": 17,
            },
        ),
        segment_spec=SegmentSpec(dimensions=["country", "device"]),
    )


def _demo_client(*, mode: str, db_url: str, api_url: str, api_token: str | None) -> DemoClient:
    if mode == "embedded":
        _ensure_sqlite_parent_dir(db_url)
        return EmbeddedCaliperClient(db_url=db_url)
    return ServiceCaliperClient(api_url=api_url, api_token=api_token)


def run_demo(*, mode: str, db_url: str, api_url: str, api_token: str | None) -> dict[str, Any]:
    workspace_id = "ws-web-demo"
    if mode == "embedded":
        _reset_sqlite_file(db_url)

    client = _demo_client(mode=mode, db_url=db_url, api_url=api_url, api_token=api_token)
    try:
        created = client.create_job(
            _build_demo_job(workspace_id=workspace_id, name=f"Web demo ({mode})")
        )
        job_id = created["job_id"] if isinstance(created, dict) else created.job_id

        client.add_arms(
            job_id=job_id,
            payload=ArmBulkRegisterRequest(
                workspace_id=workspace_id,
                arms=[
                    ArmInput(
                        arm_id="landing-a",
                        name="Landing page A",
                        arm_type=ArmType.ARTIFACT,
                        payload_ref="web://landing-a",
                        metadata={"variant": "control", "layout": "compact"},
                    ),
                    ArmInput(
                        arm_id="landing-b",
                        name="Landing page B",
                        arm_type=ArmType.ARTIFACT,
                        payload_ref="web://landing-b",
                        metadata={"variant": "challenger", "layout": "feature-heavy"},
                    ),
                ],
            ),
        )

        adapter = WebAdapter(client=client, workspace_id=workspace_id, job_id=job_id)
        chosen_counts: dict[str, int] = {"landing-a": 0, "landing-b": 0}

        requests: list[dict[str, str | int | float | bool]] = [
            {"country": "US", "device": "mobile"},
            {"country": "US", "device": "desktop"},
            {"country": "CA", "device": "mobile"},
            {"country": "US", "device": "mobile"},
            {"country": "GB", "device": "desktop"},
            {"country": "US", "device": "desktop"},
            {"country": "DE", "device": "mobile"},
            {"country": "US", "device": "mobile"},
            {"country": "CA", "device": "desktop"},
            {"country": "US", "device": "mobile"},
            {"country": "US", "device": "desktop"},
            {"country": "GB", "device": "mobile"},
        ]

        for idx, request_context in enumerate(requests, start=1):
            unit_id = f"req-{idx:03d}"
            assignment = adapter.assign_request(
                unit_id=unit_id,
                idempotency_key=f"assign-{mode}-{idx}",
                context=request_context,
            )
            chosen_counts[assignment.arm_id] += 1

            adapter.log_render(
                unit_id=unit_id,
                decision_id=assignment.decision_id,
                metadata={"path": "/pricing", "country": request_context["country"]},
            )

            click_value = 1.0 if (idx % 2 == 0 or assignment.arm_id == "landing-b") else 0.0
            conversion_value = 1.0 if (assignment.arm_id == "landing-b" and idx % 3 != 0) else 0.0

            if click_value > 0:
                adapter.log_click(
                    unit_id=unit_id,
                    decision_id=assignment.decision_id,
                    value=click_value,
                    metadata={"device": request_context["device"]},
                )

            if conversion_value > 0:
                adapter.log_conversion(
                    unit_id=unit_id,
                    decision_id=assignment.decision_id,
                    value=conversion_value,
                    metadata={"country": request_context["country"]},
                )

        report = client.generate_report(
            job_id=job_id,
            payload=ReportGenerateRequest(workspace_id=workspace_id),
        )
        report_dict = report.model_dump(mode="json")
        report_dict["assignment_counts"] = chosen_counts
        return report_dict
    finally:
        client.close()


def _write_artifacts(*, report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(report["markdown"], encoding="utf-8")
    (output_dir / "report.html").write_text(report["html"], encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Caliper web demo")
    parser.add_argument("--mode", choices=["embedded", "service"], default="embedded")
    parser.add_argument("--db-url", default="sqlite:///./data/web-demo.db")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-token", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    report = run_demo(
        mode=args.mode,
        db_url=args.db_url,
        api_url=args.api_url,
        api_token=args.api_token,
    )
    output_dir = Path(args.output_dir or f"docs/fixtures/web_demo/{args.mode}")
    _write_artifacts(report=report, output_dir=output_dir)

    print(f"web demo complete ({args.mode})")
    print(f"report_id={report['report_id']} assignments={report['assignment_counts']}")
    print(f"artifacts={output_dir}")


if __name__ == "__main__":
    main()
