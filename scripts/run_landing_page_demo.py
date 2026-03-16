from __future__ import annotations

import argparse
import json
import random
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.request import urlopen

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
from caliper_sdk import EmbeddedCaliperClient


def run_landing_page_demo(
    *,
    topic: str,
    variant_count: int,
    mode: str,
    db_url: str = "sqlite:///./data/landing-page-demo.db",
    output_root: str = "reports/landing_page_demo",
) -> dict[str, Any]:
    if variant_count < 2:
        raise ValueError("variant_count must be >= 2")

    client = EmbeddedCaliperClient(db_url=db_url)
    workspace_id = "ws-landing-page-demo"
    job = Job(
        workspace_id=workspace_id,
        name=f"Landing page demo: {topic}",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(
            reward_formula="(0.40 * click) + conversion",
            penalties=[],
            secondary_metrics=["click", "conversion"],
        ),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.THOMPSON_SAMPLING,
            params={
                "seed": 101,
                "arms": {
                    f"landing-{i}": {"successes": 12 + i, "failures": 14 - min(i, 10)}
                    for i in range(variant_count)
                },
            },
        ),
        segment_spec=SegmentSpec(dimensions=["country", "device"]),
    )
    created = client.create_job(job)
    job_id = created["job_id"] if isinstance(created, dict) else created.job_id

    variants_dir = Path(output_root) / mode / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)

    arms: list[ArmInput] = []
    for i in range(variant_count):
        arm_id = f"landing-{i}"
        html_path = variants_dir / f"{arm_id}.html"
        html_path.write_text(
            (
                "<html><body>"
                f"<h1>{topic} — Variant {i + 1}</h1>"
                f"<p>Landing variant {i + 1} for {topic}.</p>"
                "</body></html>"
            ),
            encoding="utf-8",
        )
        arms.append(
            ArmInput(
                arm_id=arm_id,
                name=f"Landing Variant {i + 1}",
                arm_type=ArmType.ARTIFACT,
                payload_ref=f"file://{html_path.resolve()}",
                metadata={"variant_index": i + 1, "topic": topic},
            )
        )

    client.add_arms(
        job_id=job_id,
        payload=ArmBulkRegisterRequest(workspace_id=workspace_id, arms=arms),
    )

    adapter = WebAdapter(client=client, workspace_id=workspace_id, job_id=job_id)
    traffic = 40
    assignments: dict[str, int] = {f"landing-{i}": 0 for i in range(variant_count)}

    server: ThreadingHTTPServer | None = None
    server_thread: threading.Thread | None = None
    base_url: str | None = None

    if mode == "live":
        handler = partial(SimpleHTTPRequestHandler, directory=str(variants_dir))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        rng = random.Random(42)
        for idx in range(traffic):
            unit_id = f"visitor-{idx:04d}"
            context: dict[str, str | int | float | bool] = {
                "country": rng.choice(["US", "CA", "GB", "DE"]),
                "device": rng.choice(["mobile", "desktop"]),
            }
            assignment = adapter.assign_request(
                unit_id=unit_id,
                idempotency_key=f"landing-{mode}-{idx}",
                context=context,
            )
            assignments[assignment.arm_id] += 1

            if base_url is not None:
                with urlopen(f"{base_url}/{assignment.arm_id}.html") as _:
                    pass

            adapter.log_render(
                unit_id=unit_id,
                decision_id=assignment.decision_id,
                metadata={"topic": topic},
            )

            arm_index = int(assignment.arm_id.split("-")[-1])
            click = 1.0 if rng.random() < (0.35 + (0.03 * arm_index)) else 0.0
            conversion = 1.0 if click > 0 and rng.random() < 0.25 else 0.0
            if click > 0:
                adapter.log_click(unit_id=unit_id, decision_id=assignment.decision_id, value=click)
            if conversion > 0:
                adapter.log_conversion(
                    unit_id=unit_id,
                    decision_id=assignment.decision_id,
                    value=conversion,
                )
    finally:
        if server is not None:
            server.shutdown()
            if server_thread is not None:
                server_thread.join(timeout=2)

    report = client.generate_report(
        job_id=job_id,
        payload=ReportGenerateRequest(workspace_id=workspace_id),
    )
    report_dict = report.model_dump(mode="json")
    leaders = report_dict.get("leaders", [])
    winner = leaders[0]["arm_id"] if leaders else "unknown"

    output_dir = Path(output_root) / mode
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "topic": topic,
        "mode": mode,
        "variant_count": variant_count,
        "winner_arm_id": winner,
        "assignment_counts": assignments,
        "report_id": report_dict["report_id"],
        "job_id": report_dict["job_id"],
        "variants_dir": str(variants_dir),
    }
    (output_dir / "report.json").write_text(
        json.dumps(report_dict, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "report.md").write_text(report_dict["markdown"], encoding="utf-8")
    (output_dir / "report.html").write_text(report_dict["html"], encoding="utf-8")
    (output_dir / "winner_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run landing page demo orchestration")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--variant-count", type=int, default=5)
    parser.add_argument("--mode", choices=["dry_run", "live"], default="dry_run")
    parser.add_argument("--db-url", default="sqlite:///./data/landing-page-demo.db")
    parser.add_argument("--output-root", default="reports/landing_page_demo")
    args = parser.parse_args()

    summary = run_landing_page_demo(
        topic=args.topic,
        variant_count=args.variant_count,
        mode=args.mode,
        db_url=args.db_url,
        output_root=args.output_root,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
