from __future__ import annotations

import argparse
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

from examples.common import build_demo_client, reset_sqlite_file, write_artifacts


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


def run_demo(*, mode: str, db_url: str, api_url: str, api_token: str | None) -> dict[str, Any]:
    workspace_id = "ws-workflow-demo"
    if mode == "embedded":
        reset_sqlite_file(db_url)
    client = build_demo_client(mode=mode, db_url=db_url, api_url=api_url, api_token=api_token)

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
    write_artifacts(report=report, output_dir=output_dir)

    print(f"workflow demo complete ({args.mode})")
    print(f"report_id={report['report_id']} assignments={report['assignment_counts']}")
    print(f"artifacts={output_dir}")


if __name__ == "__main__":
    main()
