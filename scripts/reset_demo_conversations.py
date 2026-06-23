from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONVERSATION_TABLES = ["result_cache", "conversation_turns", "conversation_states", "conversations"]
ANALYTICS_NOT_TOUCHED = [
    "data/uploaded_files.json",
    "data/uploads",
    "cache/data_catalog.json",
    "cache/manifest.json",
    "cache/tables",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely backup and reset demo conversations.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be backed up/deleted.")
    parser.add_argument("--backup", action="store_true", help="Backup conversation storage before reset.")
    parser.add_argument("--confirm-reset", action="store_true", help="Required for destructive reset.")
    args = parser.parse_args()

    root = _repo_root()
    db_path = root / "data" / "app_memory.db"
    if not db_path.exists():
        raise SystemExit(f"Conversation database not found: {db_path}")

    before = _counts(db_path)
    dry_run_report = {
        "database_path": str(db_path),
        "database_type": "sqlite",
        "tables_to_backup": CONVERSATION_TABLES,
        "tables_to_delete": CONVERSATION_TABLES,
        "counts": before,
        "analytics_not_touched": ANALYTICS_NOT_TOUCHED,
    }
    if args.dry_run:
        _write_report(root, "reset_demo_conversations_dry_run.json", dry_run_report)
        print(json.dumps(dry_run_report, ensure_ascii=False, indent=2))
        return

    if not args.confirm_reset:
        raise SystemExit("Refusing to reset without --confirm-reset")
    if not args.backup:
        raise SystemExit("Refusing to reset without --backup")

    backup_dir = _backup_database(root, db_path)
    backup_db = backup_dir / db_path.name
    integrity = _integrity_check(backup_db)
    if integrity != "ok" or not backup_db.exists() or backup_db.stat().st_size <= 0:
        raise SystemExit(f"Backup verification failed: integrity={integrity}, path={backup_db}")

    with sqlite3.connect(db_path) as con:
        con.execute("PRAGMA foreign_keys = ON")
        try:
            con.execute("BEGIN")
            deleted = {table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in CONVERSATION_TABLES}
            for table in CONVERSATION_TABLES:
                con.execute(f"DELETE FROM {table}")
            con.commit()
        except Exception:
            con.rollback()
            raise

    after = _counts(db_path)
    uploaded = _uploaded_status(root)
    report = {
        "database_path": str(db_path),
        "backup_dir": str(backup_dir),
        "backup_integrity": integrity,
        "before_counts": before,
        "deleted_counts": deleted,
        "after_counts": after,
        "uploaded_files_preserved": uploaded,
        "analytics_not_touched": ANALYTICS_NOT_TOUCHED,
    }
    _write_report(root, "reset_demo_conversations_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as con:
        return {table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in CONVERSATION_TABLES}


def _backup_database(root: Path, db_path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_dir = root / "backups" / "demo_reset" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_db = backup_dir / db_path.name
    shutil.copy2(db_path, backup_db)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_paths": [str(db_path)],
        "backup_paths": [str(backup_db)],
        "sha256": {str(backup_db): _sha256(backup_db)},
        "database_integrity": _integrity_check(backup_db),
        "git_commit": _git_commit(root),
    }
    (backup_dir / "backup_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return backup_dir


def _integrity_check(db_path: Path) -> str:
    with sqlite3.connect(db_path) as con:
        return str(con.execute("PRAGMA integrity_check").fetchone()[0])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def _uploaded_status(root: Path) -> list[dict[str, Any]]:
    path = root / "data" / "uploaded_files.json"
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "id": item.get("id"),
            "filename": item.get("filename"),
            "status": item.get("status"),
            "queryable": item.get("queryable"),
        }
        for item in records
        if isinstance(item, dict)
    ]


def _write_report(root: Path, name: str, payload: dict[str, Any]) -> None:
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
