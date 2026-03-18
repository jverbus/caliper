from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from scripts.run_email_demo import run_email_demo
from scripts.run_landing_page_demo import run_landing_page_demo

PYTHONPATH = (
    "packages/py-caliper-core/src:packages/py-caliper-storage/src:packages/py-caliper-events/src:"
    "packages/py-caliper-policies/src:packages/py-caliper-reward/src:packages/py-caliper-reports/src:"
    "packages/py-caliper-adapters/src:packages/py-sdk/src:apps"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, timeout_seconds: float = 20.0) -> None:
    started = time.time()
    while time.time() - started < timeout_seconds:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=1.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError("Timed out waiting for API health endpoint")


def _start_service_api(tmp_path: Path) -> tuple[subprocess.Popen[bytes], str]:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    db_path = tmp_path / "service-api.db"

    env = os.environ.copy()
    env["CALIPER_PROFILE"] = "embedded"
    env["CALIPER_DB_URL"] = f"sqlite:///{db_path.as_posix()}"
    env["PYTHONPATH"] = PYTHONPATH

    api_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_health(base_url)
    return api_proc, base_url


def test_run_landing_page_demo_dry_run(tmp_path: Path) -> None:
    summary = run_landing_page_demo(
        topic="AI support",
        variant_count=5,
        mode="dry_run",
        db_url=f"sqlite:///{tmp_path / 'landing.db'}",
        output_root=str(tmp_path / "landing_artifacts"),
    )

    assert summary["variant_count"] == 5
    assert summary["winner_arm_id"].startswith("landing-")
    assert summary["traffic_source"] == "synthetic_simulation"
    assert summary["backend"] == "embedded"
    assert isinstance(summary["simulated_assignment_counts"], dict)

    output_dir = tmp_path / "landing_artifacts" / "dry_run"
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    winner_summary = json.loads((output_dir / "winner_summary.json").read_text(encoding="utf-8"))
    assert "leaders" in report
    assert winner_summary["winner_arm_id"].startswith("landing-")


def test_run_landing_page_demo_dry_run_service_backend(tmp_path: Path) -> None:
    api_proc, base_url = _start_service_api(tmp_path)
    try:
        summary = run_landing_page_demo(
            topic="AI support",
            variant_count=4,
            mode="dry_run",
            backend="service",
            api_url=base_url,
            output_root=str(tmp_path / "landing_service_artifacts"),
        )
    finally:
        api_proc.terminate()
        api_proc.wait(timeout=10)

    assert summary["backend"] == "service"
    assert summary["winner_arm_id"].startswith("landing-")


def test_run_landing_page_demo_serve_and_simulate(tmp_path: Path) -> None:
    summary = run_landing_page_demo(
        topic="AI support",
        variant_count=4,
        mode="serve_and_simulate",
        backend="embedded",
        db_url=f"sqlite:///{tmp_path / 'landing-live.db'}",
        output_root=str(tmp_path / "landing_live_artifacts"),
        host="127.0.0.1",
        port=_free_port(),
        simulate_visitors=12,
        observe_seconds=0,
    )

    assert summary["mode"] == "serve_and_simulate"
    assert summary["traffic_source"] == "real_endpoints_plus_synthetic_driver"
    assert summary["demo_url"] is not None
    assert summary["report_url"] is not None
    assert summary["winner_arm_id"].startswith("landing-")


def test_run_landing_page_demo_serve_and_simulate_public_base_url(tmp_path: Path) -> None:
    public_base_url = "https://demo.example.com"
    port = _free_port()
    summary = run_landing_page_demo(
        topic="AI support",
        variant_count=4,
        mode="serve_and_simulate",
        backend="embedded",
        db_url=f"sqlite:///{tmp_path / 'landing-live-public.db'}",
        output_root=str(tmp_path / "landing_live_public_artifacts"),
        host="127.0.0.1",
        port=port,
        simulate_visitors=8,
        observe_seconds=0,
        public_base_url=public_base_url,
    )

    assert summary["public_base_url"] == public_base_url
    assert summary["demo_url"] == f"{public_base_url}/lp/{summary['job_id']}"
    assert summary["report_url"] == f"{public_base_url}/lp/{summary['job_id']}/report"
    assert summary["public_urls"]["demo_url"] == summary["demo_url"]
    assert summary["local_demo_url"] == f"http://127.0.0.1:{port}/lp/{summary['job_id']}"
    assert summary["local_report_url"] == f"http://127.0.0.1:{port}/lp/{summary['job_id']}/report"


def test_run_landing_page_demo_rejects_public_base_url_in_dry_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="public_base_url/open_tunnel require"):
        run_landing_page_demo(
            topic="AI support",
            variant_count=3,
            mode="dry_run",
            db_url=f"sqlite:///{tmp_path / 'landing-dry-run.db'}",
            output_root=str(tmp_path / "landing_dry_run_artifacts"),
            public_base_url="https://demo.example.com",
        )


def test_run_landing_page_demo_rejects_conflicting_public_url_flags(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="choose either open_tunnel or public_base_url"):
        run_landing_page_demo(
            topic="AI support",
            variant_count=3,
            mode="serve_only",
            db_url=f"sqlite:///{tmp_path / 'landing-conflict.db'}",
            output_root=str(tmp_path / "landing_conflict_artifacts"),
            public_base_url="https://demo.example.com",
            open_tunnel=True,
        )


def test_run_email_demo_dry_run(tmp_path: Path) -> None:
    summary = run_email_demo(
        topic="Launch campaign",
        recipients=[f"u{i}@example.com" for i in range(1, 7)],
        variant_count=5,
        mode="dry_run",
        db_url=f"sqlite:///{tmp_path / 'email.db'}",
        output_root=str(tmp_path / "email_artifacts"),
        tracking_port=_free_port(),
    )

    assert summary["variant_count"] == 5
    assert summary["provider_mode"] in {"dry-run-seam", "gmail"}
    assert summary["measurement"]["synthetic_driver_enabled"] is True
    assert summary["urls"]["tracking_routes"]["click"].endswith(f"/email/{summary['job_id']}/click")

    output_dir = tmp_path / "email_artifacts" / "dry_run"
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    winner_summary = json.loads((output_dir / "winner_summary.json").read_text(encoding="utf-8"))
    dispatch_manifest = json.loads(
        (output_dir / "dispatch_manifest.json").read_text(encoding="utf-8")
    )
    assert "leaders" in report
    assert winner_summary["winner_arm_id"].startswith("subject-")
    assert isinstance(dispatch_manifest, list)
    assert dispatch_manifest


def test_run_email_demo_dry_run_public_base_url(tmp_path: Path) -> None:
    public_base_url = "https://demo.example.com"
    summary = run_email_demo(
        topic="Launch campaign",
        recipients=[f"u{i}@example.com" for i in range(1, 5)],
        variant_count=4,
        mode="dry_run",
        db_url=f"sqlite:///{tmp_path / 'email-public.db'}",
        output_root=str(tmp_path / "email_public_artifacts"),
        tracking_host="127.0.0.1",
        tracking_port=_free_port(),
        public_base_url=public_base_url,
    )

    assert summary["public_base_url"] == public_base_url
    assert summary["public_urls"] is not None
    assert summary["urls"]["tracking_base_url"] == public_base_url
    assert summary["urls"]["report_url"] == f"{public_base_url}/email/{summary['job_id']}/report"
    assert summary["urls"]["local_tracking_base_url"].startswith("http://127.0.0.1:")
    assert summary["urls"]["tracking_routes"]["click"].startswith(
        f"{public_base_url}/email/{summary['job_id']}/click"
    )

    dispatch_manifest = json.loads(
        (Path(summary["artifacts"]["dispatch_manifest_json"])).read_text(encoding="utf-8")
    )
    assert dispatch_manifest
    assert dispatch_manifest[0]["tracking"]["click"].startswith(
        f"{public_base_url}/email/{summary['job_id']}/click"
    )
    assert dispatch_manifest[0]["tracking_local"]["click"].startswith(
        f"{summary['urls']['local_tracking_base_url']}/email/{summary['job_id']}/click"
    )


def test_run_email_demo_rejects_conflicting_public_url_flags(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="choose either open_tunnel or public_base_url"):
        run_email_demo(
            topic="Launch campaign",
            recipients=["u1@example.com", "u2@example.com"],
            variant_count=3,
            mode="dry_run",
            db_url=f"sqlite:///{tmp_path / 'email-conflict.db'}",
            output_root=str(tmp_path / "email_conflict_artifacts"),
            public_base_url="https://demo.example.com",
            open_tunnel=True,
        )


def test_run_email_demo_dry_run_service_backend(tmp_path: Path) -> None:
    api_proc, base_url = _start_service_api(tmp_path)
    try:
        summary = run_email_demo(
            topic="Launch campaign",
            recipients=[f"u{i}@example.com" for i in range(1, 6)],
            variant_count=4,
            mode="dry_run",
            backend="service",
            api_url=base_url,
            output_root=str(tmp_path / "email_service_artifacts"),
            tracking_port=_free_port(),
            observe_seconds=0,
        )
    finally:
        api_proc.terminate()
        api_proc.wait(timeout=10)

    assert summary["backend"] == "service"
    assert summary["winner_arm_id"].startswith("subject-")
    assert summary["measurement"]["synthetic_driver_enabled"] is True


def test_run_email_demo_live_requires_gmail_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GMAIL_SMTP_USER", raising=False)
    monkeypatch.delenv("GMAIL_SMTP_APP_PASSWORD", raising=False)
    monkeypatch.delenv("GMAIL_SMTP_FROM", raising=False)

    with pytest.raises(ValueError, match="Live mode requires Gmail SMTP credentials"):
        run_email_demo(
            topic="Launch campaign",
            recipients=[f"u{i}@example.com" for i in range(1, 4)],
            variant_count=3,
            mode="live",
            db_url=f"sqlite:///{tmp_path / 'email-live.db'}",
            output_root=str(tmp_path / "email_artifacts"),
            tracking_port=_free_port(),
            observe_seconds=0,
        )
