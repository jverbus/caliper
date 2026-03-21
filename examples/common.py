from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient

DemoClient = EmbeddedCaliperClient | ServiceCaliperClient


def sqlite_db_path(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None

    sqlite_path = db_url.removeprefix("sqlite:///")
    if not sqlite_path or sqlite_path == ":memory:":
        return None

    db_file = Path(sqlite_path)
    if not db_file.is_absolute():
        db_file = Path.cwd() / db_file
    return db_file


def ensure_sqlite_parent_dir(db_url: str) -> None:
    db_file = sqlite_db_path(db_url)
    if db_file is None:
        return
    db_file.parent.mkdir(parents=True, exist_ok=True)


def reset_sqlite_file(db_url: str) -> None:
    db_file = sqlite_db_path(db_url)
    if db_file is None:
        return
    if db_file.exists():
        db_file.unlink()


def build_demo_client(*, mode: str, db_url: str, api_url: str, api_token: str | None) -> DemoClient:
    if mode == "embedded":
        ensure_sqlite_parent_dir(db_url)
        return EmbeddedCaliperClient(db_url=db_url)
    return ServiceCaliperClient(api_url=api_url, api_token=api_token)


def write_artifacts(*, report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(report["markdown"], encoding="utf-8")
    (output_dir / "report.html").write_text(report["html"], encoding="utf-8")
