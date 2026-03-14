from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from caliper_adapters import WorkflowAdapter
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
        surface_type=SurfaceType.WORKFLOW,
        objective_spec=ObjectiveSpec(
            reward_formula="objective - llm_cost_usd - (latency_ms / 2000)",
            penalties=["0.5 * breach_rate"],
            secondary_metrics=["human_acceptance", "latency_ms", "llm_cost_usd"],
        ),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.FIXED_SPLIT,
            params={"weights": {"arm-fast": 1.0, "arm-accurate": 1.0}},
        ),
    )


def _demo_client(*, mode: str, db_url: str, api_url: str, api_token: str | None) -> DemoClient:
    if mode == "embedded":
        _ensure_sqlite_parent_dir(db_url)
        return EmbeddedCaliperClient(db_url=db_url)
    return ServiceCaliperClient(api_url=api_url, api_token=api_token)


def run_demo(*, mode: str, db_url: str, api_url: str, api_token: str | None) -> dict[str, Any]:
    workspace_id = "ws-workflow-demo"
    if mode == "embedded":
        _reset_sqlite_file(db_url)
    client = _demo_client(mode=mode, db_url=db_url, api_url=api_url, api_token=api_token)

    created = client.create_job(
        _build_demo_job(workspace_id=workspace_id, name=f"Workflow demo ({mode})")
    )
    job_id = created["job_id"] if isinstance(created, dict) else created.job_id

    client.add_arms(
        job_id=job_id,
        payload=ArmBulkRegisterRequest(
            workspace_id=workspace_id,
            arms=[
                ArmInput(
                    arm_id="arm-fast",
                    name="Fast / cheap",
                    arm_type=ArmType.WORKFLOW,
                    payload_ref="prompt://workflow-fast",
                    metadata={"model": "gpt-5.3-mini", "profile": "latency-first"},
                ),
                ArmInput(
                    arm_id="arm-accurate",
                    name="Accurate / slower",
                    arm_type=ArmType.WORKFLOW,
                    payload_ref="prompt://workflow-accurate",
                    metadata={"model": "gpt-5.3-codex", "profile": "quality-first"},
                ),
            ],
        ),
    )

    adapter = WorkflowAdapter(client=client, workspace_id=workspace_id, job_id=job_id)
    chosen_counts: dict[str, int] = {"arm-fast": 0, "arm-accurate": 0}

    for idx in range(1, 11):
        unit_id = f"run-{idx:03d}"
        assignment = adapter.assign_workflow(
            unit_id=unit_id,
            idempotency_key=f"assign-{mode}-{idx}",
            context={"workflow": "nurture", "step": idx},
        )
        chosen_counts[assignment.arm_id] += 1

        if assignment.arm_id == "arm-fast":
            objective = 0.70
            latency = 520.0
            cost = 0.009
            accepted = idx % 3 != 0
        else:
            objective = 1.0
            latency = 890.0
            cost = 0.024
            accepted = True

        adapter.log_execution_outcome(
            unit_id=unit_id,
            decision_id=assignment.decision_id,
            objective_value=objective,
            latency_ms=latency,
            cost_usd=cost,
            metadata={"mode": mode},
        )
        adapter.log_human_acceptance(
            unit_id=unit_id,
            decision_id=assignment.decision_id,
            accepted=accepted,
            reviewer="workflow-demo",
        )

    report = client.generate_report(
        job_id=job_id,
        payload=ReportGenerateRequest(workspace_id=workspace_id),
    )
    report_dict = report.model_dump(mode="json")
    report_dict["assignment_counts"] = chosen_counts
    return report_dict


def _write_artifacts(*, report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(report["markdown"], encoding="utf-8")
    (output_dir / "report.html").write_text(report["html"], encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Caliper workflow demo")
    parser.add_argument("--mode", choices=["embedded", "service"], default="embedded")
    parser.add_argument("--db-url", default="sqlite:///./data/workflow-demo.db")
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
    output_dir = Path(args.output_dir or f"docs/fixtures/workflow_demo/{args.mode}")
    _write_artifacts(report=report, output_dir=output_dir)

    print(f"workflow demo complete ({args.mode})")
    print(f"report_id={report['report_id']} assignments={report['assignment_counts']}")
    print(f"artifacts={output_dir}")


if __name__ == "__main__":
    main()
