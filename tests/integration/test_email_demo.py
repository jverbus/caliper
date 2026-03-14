from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast
from urllib.error import URLError
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run_demo(*, mode: str, db_url: str, api_url: str, api_token: str | None) -> dict[str, Any]:
    from examples.email_demo.demo import run_demo

    return run_demo(mode=mode, db_url=db_url, api_url=api_url, api_token=api_token)


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = cast(int, sock.getsockname()[1])
    sock.close()
    return port


def _wait_for_ready(url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except URLError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Service did not become ready at {url}")


def test_email_demo_embedded_mode(tmp_path: Path) -> None:
    report = _run_demo(
        mode="embedded",
        db_url=f"sqlite:///{tmp_path}/embedded-email-demo.db",
        api_url="http://127.0.0.1:9999",
        api_token=None,
    )
    assert report["job_id"]
    assert "## Guardrails" in report["markdown"]
    assert "email_unsubscribe" in report["markdown"]
    assert report["delayed_outcome_decisions"] >= 10
    assert report["active_arms_by_tranche"]["tranche-1"] == ["subject-a", "subject-b"]
    assert report["active_arms_by_tranche"]["tranche-2"] == ["subject-a"]


def test_email_demo_service_mode(tmp_path: Path) -> None:
    port = _free_port()
    db_path = tmp_path / "service-email-demo.db"
    env = os.environ.copy()
    env["CALIPER_PROFILE"] = "embedded"
    env["CALIPER_DB_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = ":".join(
        [
            "packages/py-caliper-core/src",
            "packages/py-caliper-storage/src",
            "packages/py-caliper-events/src",
            "packages/py-caliper-policies/src",
            "packages/py-caliper-reward/src",
            "packages/py-caliper-reports/src",
            "packages/py-caliper-adapters/src",
            "packages/py-sdk/src",
            "apps",
        ]
    )

    process = subprocess.Popen(
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
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_ready(f"http://127.0.0.1:{port}/health")
        report = _run_demo(
            mode="service",
            db_url=f"sqlite:///{db_path}",
            api_url=f"http://127.0.0.1:{port}",
            api_token=None,
        )
        assert report["job_id"]
        assert "## Guardrails" in report["markdown"]
        assert "email_unsubscribe" in report["markdown"]
        assert report["active_arms_by_tranche"]["tranche-2"] == ["subject-a"]
    finally:
        process.terminate()
        process.wait(timeout=10)
