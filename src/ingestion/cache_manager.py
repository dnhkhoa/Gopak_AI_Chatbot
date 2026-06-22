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
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def refresh(self, paths: list[Path], force: bool = False) -> list[dict]:
        manifest = self._read_manifest()
        tables: list[dict] = []
        for path in paths:
            digest = file_sha256(path)
            file_entry = manifest["files"].get(str(path), {})
            if not force and file_entry.get("sha256") == digest:
                tables.extend(file_entry.get("tables", []))
                continue
            loaded_tables = load_workbook_tables(path)
            file_tables = []
            for loaded in loaded_tables:
                parquet_path = self.tables_dir / f"{loaded.profile.table_name}_{digest[:12]}.parquet"
                loaded.dataframe.to_parquet(parquet_path, index=False)
                item = {
                    "table_name": loaded.profile.table_name,
                    "source_path": str(path),
                    "source_file": path.name,
                    "source_sheet": loaded.profile.source_sheet,
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

    def load_tables(self) -> list[dict]:
        return self._read_manifest().get("tables", [])

    def read_table(self, table_name: str) -> pd.DataFrame:
        for table in self.load_tables():
            if table["table_name"] == table_name:
                return pd.read_parquet(table["parquet_path"])
        raise KeyError(f"Unknown cached table: {table_name}")

