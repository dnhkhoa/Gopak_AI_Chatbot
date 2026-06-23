from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a demo conversation backup.")
    parser.add_argument("--backup-dir", required=True, help="Path to backups/demo_reset/<timestamp>.")
    parser.add_argument("--confirm-restore", action="store_true", help="Required for restore.")
    args = parser.parse_args()
    if not args.confirm_restore:
        raise SystemExit("Refusing to restore without --confirm-restore")

    root = Path(__file__).resolve().parents[1]
    target_db = root / "data" / "app_memory.db"
    backup_dir = (root / args.backup_dir).resolve() if not Path(args.backup_dir).is_absolute() else Path(args.backup_dir).resolve()
    backup_db = backup_dir / target_db.name
    manifest_path = backup_dir / "backup_manifest.json"
    if not backup_db.exists() or backup_db.stat().st_size <= 0:
        raise SystemExit(f"Backup database not found or empty: {backup_db}")
    if _integrity_check(backup_db) != "ok":
        raise SystemExit(f"Backup integrity check failed: {backup_db}")

    current_backup = _backup_current_state(root, target_db)
    shutil.copy2(backup_db, target_db)
    restored_integrity = _integrity_check(target_db)
    report = {
        "restored_from": str(backup_db),
        "source_manifest": str(manifest_path) if manifest_path.exists() else None,
        "current_state_backup": str(current_backup),
        "restored_integrity": restored_integrity,
        "target_sha256": _sha256(target_db),
        "uploaded_files_not_touched": True,
    }
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "restore_demo_conversation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _backup_current_state(root: Path, db_path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = root / "backups" / "demo_restore" / timestamp
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / db_path.name
    shutil.copy2(db_path, destination)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_paths": [str(db_path)],
        "backup_paths": [str(destination)],
        "sha256": {str(destination): _sha256(destination)},
        "database_integrity": _integrity_check(destination),
    }
    (folder / "backup_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


def _integrity_check(db_path: Path) -> str:
    with sqlite3.connect(db_path) as con:
        return str(con.execute("PRAGMA integrity_check").fetchone()[0])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
