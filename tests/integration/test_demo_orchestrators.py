from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from scripts.run_email_demo import run_email_demo
from scripts.run_landing_page_demo import run_landing_page_demo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


def test_run_email_demo_dry_run(tmp_path: Path) -> None:
    summary = run_email_demo(
        topic="Launch campaign",
        recipients=[f"u{i}@example.com" for i in range(1, 7)],
        variant_count=5,
        mode="dry_run",
        db_url=f"sqlite:///{tmp_path / 'email.db'}",
        output_root=str(tmp_path / "email_artifacts"),
    )

    assert summary["variant_count"] == 5
    assert summary["provider_mode"] in {"dry-run-seam", "gmail"}

    output_dir = tmp_path / "email_artifacts" / "dry_run"
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    winner_summary = json.loads((output_dir / "winner_summary.json").read_text(encoding="utf-8"))
    assert "leaders" in report
    assert winner_summary["winner_arm_id"].startswith("subject-")


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
        )
