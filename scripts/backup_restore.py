from __future__ import annotations

import argparse
import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

MANIFEST_NAME = "manifest.json"


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve()))


def _safe_members(members: list[tarfile.TarInfo]) -> list[tarfile.TarInfo]:
    safe: list[tarfile.TarInfo] = []
    for member in members:
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"unsafe archive member path: {member.name}")
        safe.append(member)
    return safe


def create_backup_archive(
    *, repo_root: Path, data_dir: Path, reports_dir: Path, output_file: Path
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    tracked_paths: list[Path] = []
    for path in (data_dir, reports_dir):
        resolved = path.resolve()
        if resolved.exists():
            tracked_paths.append(resolved)

    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "paths": [_repo_relative(path, repo_root=repo_root) for path in tracked_paths],
    }

    with tarfile.open(output_file, mode="w:gz") as archive:
        for path in tracked_paths:
            archive.add(path, arcname=_repo_relative(path, repo_root=repo_root))

        manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
        info = tarfile.TarInfo(name=MANIFEST_NAME)
        info.size = len(manifest_bytes)
        archive.addfile(info, fileobj=io.BytesIO(manifest_bytes))

    return {
        "archive": str(output_file),
        "tracked_paths": manifest["paths"],
    }


def restore_backup_archive(*, archive_file: Path, target_root: Path) -> dict[str, object]:
    target_root = target_root.resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_file, mode="r:gz") as archive:
        members = _safe_members(archive.getmembers())
        archive.extractall(path=target_root, members=members)

    manifest_path = target_root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    return {
        "archive": str(archive_file),
        "restored_paths": manifest.get("paths", []),
        "target_root": str(target_root),
    }


def _default_archive_name() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"caliper-backup-{stamp}.tar.gz"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup and restore Caliper local data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a backup archive")
    backup_parser.add_argument(
        "--repo-root", default=".", help="Repo root containing data/reports directories"
    )
    backup_parser.add_argument(
        "--data-dir", default="data", help="Directory containing SQLite/runtime data"
    )
    backup_parser.add_argument(
        "--reports-dir", default="reports", help="Directory containing report artifacts"
    )
    backup_parser.add_argument(
        "--output-file",
        default=None,
        help="Path for output archive (default: exports/caliper-backup-<timestamp>.tar.gz)",
    )

    restore_parser = subparsers.add_parser("restore", help="Restore from backup archive")
    restore_parser.add_argument(
        "--archive-file", required=True, help="Backup archive produced by the backup command"
    )
    restore_parser.add_argument(
        "--target-root", default=".", help="Directory to restore archive contents into"
    )

    args = parser.parse_args()

    if args.command == "backup":
        repo_root = Path(args.repo_root)
        output_file = (
            Path(args.output_file)
            if args.output_file
            else repo_root / "exports" / _default_archive_name()
        )
        summary = create_backup_archive(
            repo_root=repo_root,
            data_dir=repo_root / args.data_dir,
            reports_dir=repo_root / args.reports_dir,
            output_file=output_file,
        )
    else:
        summary = restore_backup_archive(
            archive_file=Path(args.archive_file),
            target_root=Path(args.target_root),
        )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
