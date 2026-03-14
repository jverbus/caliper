from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_seed_demo_data_module():
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    script_path = repo_root / "scripts" / "seed_demo_data.py"
    spec = importlib.util.spec_from_file_location("seed_demo_data", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load seed_demo_data module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_demo_data"] = module
    spec.loader.exec_module(module)
    return module


seed_demo_data = _load_seed_demo_data_module()


def _fake_runner(*, mode: str, db_url: str, api_url: str, api_token: str | None):
    assert mode == "embedded"
    assert db_url.startswith("sqlite:///")
    assert api_url == "http://127.0.0.1:8000"
    assert api_token is None
    return {
        "report_id": "report-123",
        "markdown": "# demo",
        "html": "<h1>demo</h1>",
    }


def test_seed_embedded_demo_data_writes_expected_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        seed_demo_data,
        "SURFACES",
        (seed_demo_data.DemoSurface("workflow", _fake_runner),),
    )

    db_dir = tmp_path / "db"
    report_dir = tmp_path / "reports"
    summary = seed_demo_data.seed_embedded_demo_data(db_dir=db_dir, report_dir=report_dir)

    assert summary == [
        {
            "surface": "workflow",
            "db_url": f"sqlite:///{(db_dir / 'workflow-demo.db').as_posix()}",
            "report_id": "report-123",
            "artifacts": str(report_dir / "workflow"),
        }
    ]

    assert (report_dir / "workflow" / "report.json").exists()
    assert (report_dir / "workflow" / "report.md").read_text(encoding="utf-8") == "# demo"
    assert (report_dir / "workflow" / "report.html").read_text(encoding="utf-8") == "<h1>demo</h1>"


def test_main_writes_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        seed_demo_data,
        "SURFACES",
        (seed_demo_data.DemoSurface("workflow", _fake_runner),),
    )

    summary_file = tmp_path / "seed" / "manifest.json"
    # argparse reads sys.argv; patch it for this call.
    monkeypatch.setattr(
        "sys.argv",
        [
            "seed_demo_data.py",
            "--db-dir",
            str(tmp_path / "db"),
            "--report-dir",
            str(tmp_path / "reports"),
            "--summary-file",
            str(summary_file),
        ],
    )

    seed_demo_data.main()

    manifest = json.loads(summary_file.read_text(encoding="utf-8"))
    assert manifest[0]["surface"] == "workflow"
    assert manifest[0]["report_id"] == "report-123"
