from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_backup_restore_module() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    script_path = repo_root / "scripts" / "backup_restore.py"
    spec = importlib.util.spec_from_file_location("backup_restore", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load backup_restore module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["backup_restore"] = module
    spec.loader.exec_module(module)
    return module


backup_restore = _load_backup_restore_module()


def test_backup_and_restore_roundtrip(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    data_dir = repo_root / "data"
    reports_dir = repo_root / "reports"
    (data_dir / "seed").mkdir(parents=True)
    (reports_dir / "seed" / "workflow").mkdir(parents=True)

    (data_dir / "seed" / "workflow-demo.db").write_text("db-content", encoding="utf-8")
    (reports_dir / "seed" / "workflow" / "report.md").write_text("# report", encoding="utf-8")

    archive_file = repo_root / "exports" / "backup.tar.gz"
    summary = backup_restore.create_backup_archive(
        repo_root=repo_root,
        data_dir=data_dir,
        reports_dir=reports_dir,
        output_file=archive_file,
    )

    assert summary["archive"] == str(archive_file)
    assert summary["tracked_paths"] == ["data", "reports"]
    assert archive_file.exists()

    restore_root = tmp_path / "restore"
    restore_summary = backup_restore.restore_backup_archive(
        archive_file=archive_file,
        target_root=restore_root,
    )

    assert restore_summary["restored_paths"] == ["data", "reports"]
    assert (restore_root / "data" / "seed" / "workflow-demo.db").read_text(
        encoding="utf-8"
    ) == "db-content"
    assert (restore_root / "reports" / "seed" / "workflow" / "report.md").read_text(
        encoding="utf-8"
    ) == "# report"

    manifest = json.loads((restore_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["paths"] == ["data", "reports"]
