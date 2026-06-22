from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from openpyxl import load_workbook
import pandas as pd

from src.config import TARGET_EXCEL_FILES
from src.ingestion.header_detector import HeaderDetection, detect_header
from src.ingestion.normalizer import (
    infer_semantic_role,
    make_unique,
    normalize_column_name,
    parse_datetime_series,
    parse_duration_seconds,
    stable_table_name,
)


@dataclass
class SheetProfile:
    source_file: str
    source_sheet: str
    table_name: str
    header_row: int
    data_start_row: int
    row_count: int
    column_count: int
    original_columns: list[str]
    normalized_columns: list[str]
    column_mapping: dict[str, str]
    semantic_roles: dict[str, str]
    issues: list[str]


@dataclass
class LoadedTable:
    profile: SheetProfile
    dataframe: pd.DataFrame


def find_excel_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for target in TARGET_EXCEL_FILES:
        matches = sorted(p for p in root.rglob(target) if p.is_file() and "~$" not in p.name)
        found.extend(matches)
    return found


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_workbook(path: Path, sample_rows: int = 100) -> list[tuple[str, HeaderDetection | None, list[list[object]], int, int]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    output = []
    for worksheet in workbook.worksheets:
        rows = [list(row) for row in worksheet.iter_rows(min_row=1, max_row=min(worksheet.max_row or 1, sample_rows), values_only=True)]
        detection = detect_header(rows)
        output.append((worksheet.title, detection, rows, worksheet.max_row or 0, worksheet.max_column or 0))
    return output


def _is_blank_row(row: list[object]) -> bool:
    return all(value is None or str(value).strip() == "" for value in row)


def _is_repeated_header(row: list[object], headers: list[str]) -> bool:
    values = ["" if value is None else str(value).strip() for value in row]
    matches = sum(1 for a, b in zip(values, headers) if a and a == b)
    return matches >= max(2, len([h for h in headers if h]) // 2)


def _is_total_row(row: list[object]) -> bool:
    text = " ".join(str(value).strip().lower() for value in row if value is not None)
    return text.startswith(("total", "grand total", "tổng", "tổng cộng"))


def load_workbook_tables(path: Path) -> list[LoadedTable]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    import_id = str(uuid4())
    loaded: list[LoadedTable] = []
    for worksheet in workbook.worksheets:
        sample = [list(row) for row in worksheet.iter_rows(min_row=1, max_row=min(worksheet.max_row or 1, 100), values_only=True)]
        detection = detect_header(sample)
        if detection is None:
            continue
        header_row_excel = detection.header_row_index + 1
        header_cells = sample[detection.header_row_index]
        start, end = detection.start_column_index, detection.end_column_index
        original_headers = ["" if value is None else str(value).strip() for value in header_cells[start : end + 1]]
        normalized = make_unique([normalize_column_name(name, i) for i, name in enumerate(original_headers)])

        records: list[dict[str, object]] = []
        for excel_row, raw_row in enumerate(worksheet.iter_rows(min_row=header_row_excel + 1, values_only=True), start=header_row_excel + 1):
            row = list(raw_row)[start : end + 1]
            if _is_blank_row(row):
                if records:
                    # Ignore trailing report whitespace; keep scanning if blanks are interspersed before data.
                    continue
                continue
            if _is_repeated_header(row, original_headers) or _is_total_row(row):
                continue
            record = dict(zip(normalized, row))
            record["_source_file"] = path.name
            record["_source_sheet"] = worksheet.title
            record["_source_row"] = excel_row
            record["_import_id"] = import_id
            records.append(record)

        df = pd.DataFrame.from_records(records)
        issues: list[str] = []
        if df.empty:
            issues.append("No data rows detected after header.")
        else:
            blankish = []
            for original, col in zip(original_headers, normalized):
                if col not in df.columns:
                    continue
                numeric_artifact = original.strip().isdigit() or not original.strip()
                almost_empty = df[col].notna().sum() <= 1
                if df[col].isna().all() or (numeric_artifact and almost_empty):
                    blankish.append(col)
            if blankish:
                df = df.drop(columns=blankish)
                kept = [(orig, norm) for orig, norm in zip(original_headers, normalized) if norm not in blankish]
                original_headers = [orig for orig, _ in kept]
                normalized = [norm for _, norm in kept]
                issues.append(f"Dropped all-null columns: {', '.join(blankish)}")

            for original, column in zip(original_headers, normalized):
                role = infer_semantic_role(column, original)
                if role in {"start_time", "end_time"}:
                    df[column] = parse_datetime_series(df[column])
                elif role == "duration":
                    df[f"{column}_seconds"] = df[column].map(parse_duration_seconds)
                    issues.append(f"Added parsed duration seconds column: {column}_seconds")

        semantic_roles = {
            column: role
            for original, column in zip(original_headers, normalized)
            if (role := infer_semantic_role(column, original))
        }
        for column in list(df.columns):
            if column.endswith("_seconds"):
                semantic_roles[column] = "duration_seconds"

        table_name = stable_table_name(path.name, worksheet.title)
        profile = SheetProfile(
            source_file=path.name,
            source_sheet=worksheet.title,
            table_name=table_name,
            header_row=header_row_excel,
            data_start_row=header_row_excel + 1,
            row_count=len(df),
            column_count=len(df.columns),
            original_columns=original_headers,
            normalized_columns=list(df.columns),
            column_mapping=dict(zip(original_headers, normalized)),
            semantic_roles=semantic_roles,
            issues=issues,
        )
        loaded.append(LoadedTable(profile=profile, dataframe=df))
    return loaded


def profile_to_dict(profile: SheetProfile) -> dict:
    return asdict(profile)
