from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.ingestion.workbook_scanner import LoadedTable, file_sha256, load_workbook_tables, profile_to_dict


class ParquetCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.tables_dir = cache_dir / "tables"
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = cache_dir / "manifest.json"

    def _read_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {"files": {}, "tables": []}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, manifest: dict) -> None:
        tmp_path = self.manifest_path.with_suffix(self.manifest_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp_path.replace(self.manifest_path)

    def refresh(self, paths: list[Path], force: bool = False) -> list[dict]:
        manifest = self._read_manifest()
        tables: list[dict] = []
        for path in paths:
            digest = file_sha256(path)
            file_entry = manifest["files"].get(str(path), {})
            if not force and file_entry.get("sha256") == digest:
                tables.extend(file_entry.get("tables", []))
                continue
            loaded_tables = load_workbook_tables(path, source_file_name=path.name, source_file_id=digest[:16])
            file_tables = []
            for loaded in loaded_tables:
                parquet_path = self.tables_dir / f"{loaded.profile.table_name}_{digest[:12]}.parquet"
                loaded.dataframe.to_parquet(parquet_path, index=False)
                item = {
                    "table_name": loaded.profile.table_name,
                    "source_path": str(path),
                    "source_file": path.name,
                    "source_sheet": loaded.profile.source_sheet,
                    "file_id": digest[:16],
                    "source_file_id": digest[:16],
                    "sha256": digest,
                    "parquet_path": str(parquet_path),
                    "profile": profile_to_dict(loaded.profile),
                }
                file_tables.append(item)
                tables.append(item)
            manifest["files"][str(path)] = {"sha256": digest, "tables": file_tables}
        manifest["tables"] = [table for file_info in manifest["files"].values() for table in file_info.get("tables", [])]
        self._write_manifest(manifest)
        return manifest["tables"]

    def refresh_uploaded_file(
        self,
        *,
        file_id: str,
        source_path: Path,
        original_filename: str,
        sha256: str,
        force: bool = True,
    ) -> list[dict]:
        manifest = self._read_manifest()
        key = f"uploaded:{file_id}"
        file_entry = manifest["files"].get(key, {})
        if not force and file_entry.get("sha256") == sha256:
            return file_entry.get("tables", [])

        old_tables = file_entry.get("tables", [])
        for old in old_tables:
            path = Path(str(old.get("parquet_path", "")))
            if path.exists() and path.parent == self.tables_dir:
                path.unlink()

        loaded_tables = load_workbook_tables(source_path, source_file_name=original_filename, source_file_id=file_id)
        file_tables = []
        for loaded in loaded_tables:
            parquet_path = self.tables_dir / f"{loaded.profile.table_name}_{file_id[:12]}.parquet"
            loaded.dataframe.to_parquet(parquet_path, index=False)
            item = {
                "table_name": loaded.profile.table_name,
                "source_path": str(source_path),
                "source_file": original_filename,
                "source_sheet": loaded.profile.source_sheet,
                "file_id": file_id,
                "source_file_id": file_id,
                "sha256": sha256,
                "parquet_path": str(parquet_path),
                "profile": profile_to_dict(loaded.profile),
            }
            file_tables.append(item)
        manifest["files"][key] = {"sha256": sha256, "tables": file_tables, "source_path": str(source_path), "source_file": original_filename}
        manifest["tables"] = [table for file_info in manifest["files"].values() for table in file_info.get("tables", [])]
        self._write_manifest(manifest)
        return file_tables

    def remove_file(self, file_id: str) -> list[dict]:
        manifest = self._read_manifest()
        key = f"uploaded:{file_id}"
        removed = manifest["files"].pop(key, {}).get("tables", [])
        for table in removed:
            path = Path(str(table.get("parquet_path", "")))
            if path.exists() and path.parent == self.tables_dir:
                path.unlink()
        manifest["tables"] = [table for file_info in manifest["files"].values() for table in file_info.get("tables", [])]
        self._write_manifest(manifest)
        return removed

    def load_tables(self) -> list[dict]:
        return self._read_manifest().get("tables", [])

    def read_table(self, table_name: str) -> pd.DataFrame:
        for table in self.load_tables():
            if table["table_name"] == table_name:
                return pd.read_parquet(table["parquet_path"])
        raise KeyError(f"Unknown cached table: {table_name}")
