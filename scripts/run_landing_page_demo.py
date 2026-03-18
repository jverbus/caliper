from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
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

from scripts.tunnel_helpers import (
    QuickTunnelHandle,
    normalize_public_base_url,
    start_cloudflared_quick_tunnel,
)


def _build_client(
    *,
    backend: str,
    db_url: str,
    api_url: str,
    api_token: str | None,
) -> EmbeddedCaliperClient | ServiceCaliperClient:
    if backend == "service":
        return ServiceCaliperClient(api_url=api_url, api_token=api_token)
    if backend == "embedded":
        return EmbeddedCaliperClient(db_url=db_url)
    msg = f"Unsupported backend: {backend!r}"
    raise ValueError(msg)


def _extract_job_id(created: dict[str, Any] | Job) -> str:
    return created["job_id"] if isinstance(created, dict) else created.job_id


def _demo_pythonpath(repo_root: Path) -> str:
    entries = [
        str(repo_root),
        str(repo_root / "packages/py-caliper-core/src"),
        str(repo_root / "packages/py-caliper-storage/src"),
        str(repo_root / "packages/py-caliper-events/src"),
        str(repo_root / "packages/py-caliper-policies/src"),
        str(repo_root / "packages/py-caliper-reward/src"),
        str(repo_root / "packages/py-caliper-reports/src"),
        str(repo_root / "packages/py-caliper-adapters/src"),
        str(repo_root / "packages/py-sdk/src"),
        str(repo_root / "apps"),
    ]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        entries.append(existing)
    return os.pathsep.join(entries)


def _variant_html(*, topic: str, index: int, variant_count: int) -> str:
    angles = [
        "Outcome-led",
        "Speed-led",
        "Reliability-led",
        "Cost-led",
        "Operator-led",
        "Trust-led",
        "Integration-led",
    ]
    ctas = [
        "Start free pilot",
        "Book a demo",
        "See the architecture",
        "Talk to sales",
        "Run ROI estimate",
    ]
    accent_palette = [
        ("#06b6d4", "#0f172a"),
        ("#22c55e", "#052e16"),
        ("#f59e0b", "#1f2937"),
        ("#8b5cf6", "#111827"),
        ("#f43f5e", "#0f172a"),
    ]
    accent, text_on_accent = accent_palette[index % len(accent_palette)]
    angle = angles[index % len(angles)]
    cta = ctas[index % len(ctas)]

    return f"""<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
    <title>{topic} — Variant {index + 1}</title>
    <style>
      :root {{
        --accent: {accent};
        --accent-text: {text_on_accent};
      }}
      body {{
        margin: 0;
        font-family: Inter, system-ui, -apple-system, sans-serif;
        background: radial-gradient(circle at top, #1e293b, #0f172a 55%);
        color: #e2e8f0;
      }}
      .container {{
        max-width: 900px;
        margin: 48px auto;
        padding: 0 20px;
      }}
      .card {{
        background: rgba(15, 23, 42, 0.82);
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 20px;
        padding: 30px;
        box-shadow: 0 25px 60px rgba(2, 6, 23, 0.45);
      }}
      .eyebrow {{
        display: inline-block;
        background: rgba(148, 163, 184, 0.15);
        border-radius: 999px;
        padding: 6px 12px;
        font-size: 12px;
        letter-spacing: .05em;
        text-transform: uppercase;
      }}
      h1 {{
        margin: 16px 0 10px;
        font-size: clamp(30px, 4.8vw, 50px);
        line-height: 1.05;
      }}
      p {{
        font-size: 18px;
        color: #cbd5e1;
        line-height: 1.55;
      }}
      .cta {{
        display: inline-block;
        margin-top: 22px;
        background: var(--accent);
        color: var(--accent-text);
        text-decoration: none;
        font-weight: 800;
        border-radius: 12px;
        padding: 12px 18px;
      }}
      .meta {{
        margin-top: 16px;
        color: #94a3b8;
        font-size: 14px;
      }}
    </style>
  </head>
  <body>
    <div class=\"container\">
      <div class=\"card\">
        <span class=\"eyebrow\">Variant {index + 1}/{variant_count} · {angle}</span>
        <h1>{topic}</h1>
        <p>
          This page emphasizes <strong>{angle.lower()}</strong> messaging for
          decision-makers evaluating AI operations tooling.
        </p>
        <a class=\"cta\" href=\"{{CTA_URL}}\">{cta}</a>
        <div class=\"meta\">Generated automatically by Caliper landing demo orchestration.</div>
      </div>
    </div>
  </body>
</html>
"""


def _generate_variants(
    *,
    topic: str,
    variant_count: int,
    variants_dir: Path,
) -> tuple[list[ArmInput], dict[str, str]]:
    variants_dir.mkdir(parents=True, exist_ok=True)
    arms: list[ArmInput] = []
    manifest: dict[str, str] = {}

    for i in range(variant_count):
        arm_id = f"landing-{i}"
        html_path = variants_dir / f"{arm_id}.html"
        html_path.write_text(
            _variant_html(topic=topic, index=i, variant_count=variant_count),
            encoding="utf-8",
        )
        manifest[arm_id] = str(html_path.resolve())
        arms.append(
            ArmInput(
                arm_id=arm_id,
                name=f"Landing Variant {i + 1}",
                arm_type=ArmType.ARTIFACT,
                payload_ref=f"file://{html_path.resolve()}",
                metadata={"variant_index": i + 1, "topic": topic},
            )
        )

    return arms, manifest


def _run_inprocess_simulation(
    *,
    adapter: WebAdapter,
    variant_count: int,
    visitor_count: int,
    seed: int,
    idempotency_prefix: str,
    topic: str,
) -> dict[str, int]:
    rng = random.Random(seed)
    assignments: dict[str, int] = {f"landing-{i}": 0 for i in range(variant_count)}

    for idx in range(visitor_count):
        unit_id = f"visitor-{idx:04d}"
        context: dict[str, str | int | float | bool] = {
            "country": rng.choice(["US", "CA", "GB", "DE"]),
            "device": rng.choice(["mobile", "desktop"]),
            "referrer": rng.choice(["direct", "search", "social"]),
        }
        assignment = adapter.assign_request(
            unit_id=unit_id,
            idempotency_key=f"{idempotency_prefix}-{idx}",
            context=context,
        )
        assignments[assignment.arm_id] = assignments.get(assignment.arm_id, 0) + 1

        adapter.log_render(
            unit_id=unit_id,
            decision_id=assignment.decision_id,
            metadata={"topic": topic, "source": "landing_demo_inprocess"},
        )

        arm_index = int(assignment.arm_id.split("-")[-1])
        click = rng.random() < (0.30 + (0.04 * arm_index))
        convert = click and (rng.random() < 0.22)
        if click:
            adapter.log_click(
                unit_id=unit_id,
                decision_id=assignment.decision_id,
                metadata={"source": "landing_demo_inprocess"},
            )
        if convert:
            adapter.log_conversion(
                unit_id=unit_id,
                decision_id=assignment.decision_id,
                metadata={"source": "landing_demo_inprocess"},
            )

    return assignments


def _wait_for_server(*, base_url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=1.5)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    msg = f"Landing demo server did not become healthy within {timeout_seconds:.1f}s"
    raise RuntimeError(msg)


def _run_http_simulation(
    *,
    base_url: str,
    job_id: str,
    variant_count: int,
    visitor_count: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed)
    assignments: dict[str, int] = {f"landing-{i}": 0 for i in range(variant_count)}
    browser_event_counts: dict[str, int] = {"click_detail": 0, "time_spent": 0}
    browser_click_metadata_examples: list[dict[str, Any]] = []
    total_time_spent_seconds = 0.0

    for idx in range(visitor_count):
        params = {
            "visitor_id": f"live-{uuid4().hex[:10]}",
            "country": rng.choice(["US", "CA", "GB", "DE"]),
            "device": rng.choice(["mobile", "desktop"]),
            "referrer": rng.choice(["direct", "search", "social"]),
        }
        with httpx.Client(timeout=10.0, follow_redirects=False) as session:
            landing = session.get(f"{base_url}/lp/{job_id}", params=params)
            landing.raise_for_status()
            arm_id = session.cookies.get("caliper_arm_id") or "unknown"
            assignments[arm_id] = assignments.get(arm_id, 0) + 1

            decision_id = session.cookies.get("caliper_decision_id")
            visitor_id = session.cookies.get("caliper_visitor_id")

            if arm_id.startswith("landing-"):
                arm_index = int(arm_id.split("-")[-1])
            else:
                arm_index = idx % max(variant_count, 1)

            click = rng.random() < (0.30 + (0.04 * arm_index))
            convert = click and (rng.random() < 0.22)
            if click:
                click_response = session.get(f"{base_url}/lp/{job_id}/click")
                if click_response.status_code >= 400:
                    click_response.raise_for_status()
            if convert:
                convert_response = session.post(f"{base_url}/lp/{job_id}/convert")
                if convert_response.status_code >= 400:
                    convert_response.raise_for_status()

            if decision_id and visitor_id:
                events: list[dict[str, Any]] = []
                if click:
                    click_metadata = {
                        "tag": "a",
                        "text": "Learn more",
                        "caliper_click_role": "cta_primary",
                        "source": "browser_tracker",
                    }
                    events.append(
                        {
                            "event_type": "click_detail",
                            "event_id": f"browser-click-{uuid4().hex}",
                            "value": 1.0,
                            "metadata": click_metadata,
                        }
                    )
                    browser_event_counts["click_detail"] += 1
                    if len(browser_click_metadata_examples) < 5:
                        browser_click_metadata_examples.append(click_metadata)

                time_spent_seconds = round(rng.uniform(1.2, 12.0), 3)
                events.append(
                    {
                        "event_type": "time_spent",
                        "event_id": f"browser-time-{uuid4().hex}",
                        "value": time_spent_seconds,
                        "metadata": {
                            "measurement": "visible_time",
                            "reason": "synthetic_browser_driver",
                            "source": "browser_tracker",
                        },
                    }
                )
                browser_event_counts["time_spent"] += 1
                total_time_spent_seconds += time_spent_seconds

                telemetry_response = session.post(
                    f"{base_url}/lp/{job_id}/events",
                    json={
                        "visitor_id": visitor_id,
                        "decision_id": decision_id,
                        "events": events,
                    },
                )
                if telemetry_response.status_code >= 400:
                    telemetry_response.raise_for_status()

    return {
        "assignment_counts": assignments,
        "browser_event_counts": browser_event_counts,
        "browser_click_metadata_examples": browser_click_metadata_examples,
        "browser_time_spent_seconds": round(total_time_spent_seconds, 3),
    }


def run_landing_page_demo(
    *,
    topic: str,
    variant_count: int,
    mode: str,
    backend: str = "embedded",
    db_url: str = "sqlite:///./data/landing-page-demo.db",
    api_url: str = "http://127.0.0.1:8000",
    api_token: str | None = None,
    output_root: str = "reports/landing_page_demo",
    host: str = "127.0.0.1",
    port: int = 8765,
    simulate_visitors: int = 120,
    observe_seconds: int = 60,
    public_base_url: str | None = None,
    open_tunnel: bool = False,
    cloudflared_bin: str = "cloudflared",
    tunnel_timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    if variant_count < 2:
        raise ValueError("variant_count must be >= 2")

    canonical_mode = "serve_and_simulate" if mode == "live" else mode
    if canonical_mode not in {"dry_run", "serve_only", "serve_and_simulate"}:
        msg = f"Unsupported mode: {mode!r}"
        raise ValueError(msg)

    if open_tunnel and public_base_url:
        raise ValueError("choose either open_tunnel or public_base_url, not both")
    if canonical_mode == "dry_run" and (open_tunnel or public_base_url):
        raise ValueError("public_base_url/open_tunnel require a served landing demo mode")

    normalized_public_base_url = (
        normalize_public_base_url(public_base_url) if public_base_url else None
    )

    client = _build_client(
        backend=backend,
        db_url=db_url,
        api_url=api_url,
        api_token=api_token,
    )

    workspace_id = "ws-landing-page-demo"
    job = Job(
        workspace_id=workspace_id,
        name=f"Landing page demo: {topic}",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(
            reward_formula="(0.40 * click) + conversion",
            penalties=[],
            secondary_metrics=["click", "conversion", "click_detail", "time_spent"],
        ),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.THOMPSON_SAMPLING,
            params={
                "seed": 101,
                "alpha": {f"landing-{i}": 12.0 + i for i in range(variant_count)},
                "beta": {f"landing-{i}": 14.0 - min(i, 10) for i in range(variant_count)},
            },
        ),
        segment_spec=SegmentSpec(dimensions=["country", "device", "referrer"]),
    )
    created = client.create_job(job)
    job_id = _extract_job_id(created)

    mode_output = "live" if canonical_mode == "serve_and_simulate" else canonical_mode
    output_dir = Path(output_root) / mode_output
    variants_dir = output_dir / "variants"

    arms, variant_manifest = _generate_variants(
        topic=topic,
        variant_count=variant_count,
        variants_dir=variants_dir,
    )

    client.add_arms(
        job_id=job_id,
        payload=ArmBulkRegisterRequest(workspace_id=workspace_id, arms=arms),
    )

    adapter = WebAdapter(client=client, workspace_id=workspace_id, job_id=job_id)

    simulated_assignments: dict[str, int] = {}
    browser_tracker_event_counts: dict[str, int] = {"click_detail": 0, "time_spent": 0}
    browser_click_metadata_examples: list[dict[str, Any]] = []
    browser_time_spent_seconds = 0.0
    demo_url: str | None = None
    report_url: str | None = None
    local_demo_url: str | None = None
    local_report_url: str | None = None
    resolved_public_base_url = normalized_public_base_url
    server_log_path: Path | None = None
    tunnel_handle: QuickTunnelHandle | None = None

    if canonical_mode == "dry_run":
        simulated_assignments = _run_inprocess_simulation(
            adapter=adapter,
            variant_count=variant_count,
            visitor_count=simulate_visitors,
            seed=42,
            idempotency_prefix=f"landing-dry-run-{job_id}",
            topic=topic,
        )
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        config_path = output_dir / "server_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "backend": backend,
                    "workspace_id": workspace_id,
                    "job_id": job_id,
                    "topic": topic,
                    "variant_manifest": variant_manifest,
                    "db_url": db_url,
                    "api_url": api_url,
                    "api_token": api_token,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        server_log_path = output_dir / "server.log"
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["CALIPER_DEMO_WEB_CONFIG"] = str(config_path.resolve())
        env["PYTHONPATH"] = _demo_pythonpath(repo_root)
        log_handle = server_log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(
            [
                "uv",
                "run",
                "uvicorn",
                "apps.demo_web.main:app",
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=str(repo_root),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        local_base_url = f"http://{host}:{port}"
        local_demo_url = f"{local_base_url}/lp/{job_id}"
        local_report_url = f"{local_base_url}/lp/{job_id}/report"

        try:
            _wait_for_server(base_url=local_base_url)

            if open_tunnel:
                tunnel_handle = start_cloudflared_quick_tunnel(
                    local_url=local_base_url,
                    output_dir=output_dir,
                    cloudflared_bin=cloudflared_bin,
                    timeout_seconds=tunnel_timeout_seconds,
                )
                resolved_public_base_url = tunnel_handle.public_base_url

            canonical_base_url = resolved_public_base_url or local_base_url
            demo_url = f"{canonical_base_url}/lp/{job_id}"
            report_url = f"{canonical_base_url}/lp/{job_id}/report"

            if canonical_mode == "serve_and_simulate":
                http_simulation = _run_http_simulation(
                    base_url=local_base_url,
                    job_id=job_id,
                    variant_count=variant_count,
                    visitor_count=simulate_visitors,
                    seed=42,
                )
                simulated_assignments = dict(http_simulation["assignment_counts"])
                browser_tracker_event_counts = dict(http_simulation["browser_event_counts"])
                browser_click_metadata_examples = list(
                    http_simulation["browser_click_metadata_examples"]
                )
                browser_time_spent_seconds = float(http_simulation["browser_time_spent_seconds"])
            else:
                if observe_seconds > 0:
                    time.sleep(observe_seconds)
        finally:
            if tunnel_handle is not None:
                tunnel_handle.stop()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            log_handle.close()

    report = client.generate_report(
        job_id=job_id,
        payload=ReportGenerateRequest(workspace_id=workspace_id),
    )
    report_dict = report.model_dump(mode="json")
    leaders = report_dict.get("leaders", [])
    winner = leaders[0]["arm_id"] if leaders else "unknown"

    output_dir.mkdir(parents=True, exist_ok=True)
    traffic_source = {
        "dry_run": "synthetic_simulation",
        "serve_only": "real_visitor_traffic_only",
        "serve_and_simulate": "real_endpoints_plus_synthetic_driver",
    }[canonical_mode]

    summary = {
        "manifest_version": "demo-orchestrator-landing-v3",
        "surface": "web",
        "topic": topic,
        "mode": canonical_mode,
        "backend": backend,
        "provider_mode": {
            "dry_run": "inprocess-simulator",
            "serve_only": "http-server",
            "serve_and_simulate": "http-server-plus-synthetic-driver",
        }[canonical_mode],
        "variant_count": variant_count,
        "winner_arm_id": winner,
        "simulated_assignment_counts": simulated_assignments,
        "traffic_source": traffic_source,
        "demo_url": demo_url,
        "report_url": report_url,
        "public_base_url": resolved_public_base_url,
        "public_urls": (
            {"demo_url": demo_url, "report_url": report_url} if resolved_public_base_url else None
        ),
        "local_demo_url": local_demo_url,
        "local_report_url": local_report_url,
        "report_id": report_dict["report_id"],
        "job_id": report_dict["job_id"],
        "variants_dir": str(variants_dir),
        "server_log": str(server_log_path) if server_log_path else None,
        "urls": {
            "demo_url": demo_url,
            "report_url": report_url,
            "public_base_url": resolved_public_base_url,
            "local_demo_url": local_demo_url,
            "local_report_url": local_report_url,
        },
        "measurement": {
            "traffic_source": traffic_source,
            "synthetic_driver_enabled": canonical_mode in {"dry_run", "serve_and_simulate"},
            "browser_tracker_enabled": canonical_mode in {"serve_only", "serve_and_simulate"},
            "event_source_labels": [
                "browser_tracker",
                "landing_demo_server",
                "landing_demo_inprocess",
            ],
            "simulated_visitor_count": sum(simulated_assignments.values()),
            "browser_tracker_event_counts": browser_tracker_event_counts,
            "browser_tracker_time_spent_seconds": round(browser_time_spent_seconds, 3),
        },
        "browser_tracker": {
            "event_source": "browser_tracker",
            "event_counts": browser_tracker_event_counts,
            "time_spent_seconds": round(browser_time_spent_seconds, 3),
            "click_metadata_examples": browser_click_metadata_examples,
        },
        "metrics": {
            "reward_formula": job.objective_spec.reward_formula,
            "secondary_metrics": job.objective_spec.secondary_metrics,
            "leaders": leaders,
            "browser_click_metadata_examples": browser_click_metadata_examples,
        },
        "artifacts": {
            "report_json": str(output_dir / "report.json"),
            "report_md": str(output_dir / "report.md"),
            "report_html": str(output_dir / "report.html"),
            "winner_summary_json": str(output_dir / "winner_summary.json"),
            "variants_dir": str(variants_dir),
            "server_config": str(output_dir / "server_config.json")
            if canonical_mode != "dry_run"
            else None,
            "server_log": str(server_log_path) if server_log_path else None,
            "cloudflared_tunnel_log": str(tunnel_handle.log_path) if tunnel_handle else None,
        },
    }

    (output_dir / "report.json").write_text(
        json.dumps(report_dict, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "report.md").write_text(report_dict["markdown"], encoding="utf-8")
    (output_dir / "report.html").write_text(report_dict["html"], encoding="utf-8")
    (output_dir / "winner_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run landing page demo orchestration")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--variant-count", type=int, default=5)
    parser.add_argument(
        "--mode",
        choices=["dry_run", "serve_only", "serve_and_simulate", "live"],
        default="dry_run",
        help=(
            "dry_run = in-process synthetic simulation; "
            "serve_only = run real HTTP demo server and wait for traffic; "
            "serve_and_simulate = real HTTP demo server + synthetic traffic driver; "
            "live is an alias of serve_and_simulate"
        ),
    )
    parser.add_argument("--backend", choices=["embedded", "service"], default="embedded")
    parser.add_argument("--db-url", default="sqlite:///./data/landing-page-demo.db")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-token", default=None)
    parser.add_argument("--output-root", default="reports/landing_page_demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--simulate-visitors",
        type=int,
        default=120,
        help="Synthetic visitor count for dry_run and serve_and_simulate modes",
    )
    parser.add_argument(
        "--observe-seconds",
        type=int,
        default=60,
        help="In serve_only mode, time window to wait for real traffic before report generation",
    )
    parser.add_argument(
        "--public-base-url",
        default=None,
        help=(
            "Externally reachable base URL used in demo/report links (for example a tunnel URL). "
            "If omitted, local host:port URLs are used."
        ),
    )
    parser.add_argument(
        "--open-tunnel",
        action="store_true",
        help="Start a Cloudflare quick tunnel after local health check and use its URL",
    )
    parser.add_argument(
        "--cloudflared-bin",
        default="cloudflared",
        help="cloudflared executable name/path used with --open-tunnel",
    )
    parser.add_argument(
        "--tunnel-timeout-seconds",
        type=float,
        default=30.0,
        help="How long to wait for cloudflared tunnel URL discovery",
    )
    args = parser.parse_args()

    summary = run_landing_page_demo(
        topic=args.topic,
        variant_count=args.variant_count,
        mode=args.mode,
        backend=args.backend,
        db_url=args.db_url,
        api_url=args.api_url,
        api_token=args.api_token,
        output_root=args.output_root,
        host=args.host,
        port=args.port,
        simulate_visitors=args.simulate_visitors,
        observe_seconds=args.observe_seconds,
        public_base_url=args.public_base_url,
        open_tunnel=args.open_tunnel,
        cloudflared_bin=args.cloudflared_bin,
        tunnel_timeout_seconds=args.tunnel_timeout_seconds,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
