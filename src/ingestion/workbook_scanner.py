from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

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
    last_data_row: int | None
    first_column: str | None
    last_column: str | None
    header_confidence: float
    header_evidence: list[str]
    original_columns: list[str]
    normalized_columns: list[str]
    column_mapping: dict[str, str]
    semantic_roles: dict[str, str]
    issues: list[str]
    validation: dict[str, object]


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


def scan_workbook(path: Path, sample_rows: int = 200) -> list[tuple[str, HeaderDetection | None, list[list[object]], int, int]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    output = []
    try:
        for worksheet in workbook.worksheets:
            max_row = worksheet.max_row or 1
            rows = [list(row) for row in worksheet.iter_rows(min_row=1, max_row=min(max_row, sample_rows), values_only=True)]
            detection = detect_header(rows)
            output.append((worksheet.title, detection, rows, worksheet.max_row or 0, worksheet.max_column or 0))
        return output
    finally:
        workbook.close()


def _is_blank_row(row: list[object]) -> bool:
    return all(value is None or str(value).strip() == "" for value in row)


def _is_repeated_header(row: list[object], headers: list[str]) -> bool:
    values = ["" if value is None else str(value).strip() for value in row]
    matches = sum(1 for a, b in zip(values, headers) if a and a == b)
    return matches >= max(2, len([h for h in headers if h]) // 2)


def _is_total_row(row: list[object]) -> bool:
    text = " ".join(str(value).strip().lower() for value in row if value is not None)
    return text.startswith(("total", "grand total", "tong", "tong cong"))


def _source_file_id(path: Path) -> str:
    return file_sha256(path)[:16]


def _cell_text(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)


def _duration_calculated_seconds(row: pd.Series, start_col: str | None, end_col: str | None) -> float | None:
    if not start_col or not end_col or start_col not in row or end_col not in row:
        return None
    start, end = row[start_col], row[end_col]
    if pd.isna(start) or pd.isna(end):
        return None
    try:
        seconds = (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds()
    except Exception:
        return None
    return float(seconds) if seconds >= 0 else None


def _add_duplicate_flags(df: pd.DataFrame, event_columns: list[str]) -> None:
    if df.empty or not event_columns:
        df["_is_exact_duplicate"] = False
        df["_duplicate_group_id"] = None
        df["_duplicate_group_size"] = 1
        return
    keys = df[event_columns].astype("string").fillna("<NA>").agg("|".join, axis=1)
    counts = keys.value_counts()
    codes = pd.factorize(keys)[0] + 1
    sizes = keys.map(counts).astype(int)
    df["_duplicate_group_size"] = sizes
    df["_is_exact_duplicate"] = sizes > 1
    df["_duplicate_group_id"] = [f"dup-{code}" if size > 1 else None for code, size in zip(codes, sizes)]


def _add_overlap_flags(df: pd.DataFrame, machine_col: str | None, start_col: str | None, end_col: str | None) -> int:
    df["_overlaps_same_machine"] = False
    if df.empty or not machine_col or not start_col or not end_col:
        return 0
    overlap_count = 0
    for _, group in df.sort_values([machine_col, start_col]).groupby(machine_col, dropna=False):
        previous_end = None
        previous_index = None
        for index, row in group.iterrows():
            start, end = row.get(start_col), row.get(end_col)
            if pd.isna(start) or pd.isna(end):
                continue
            if previous_end is not None and pd.Timestamp(start) < pd.Timestamp(previous_end):
                df.at[index, "_overlaps_same_machine"] = True
                if previous_index is not None:
                    df.at[previous_index, "_overlaps_same_machine"] = True
                overlap_count += 1
            if previous_end is None or pd.Timestamp(end) > pd.Timestamp(previous_end):
                previous_end = end
                previous_index = index
    return overlap_count


def load_workbook_tables(path: Path, source_file_name: str | None = None, source_file_id: str | None = None) -> list[LoadedTable]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    import_id = str(uuid4())
    display_name = source_file_name or path.name
    source_file_id = source_file_id or _source_file_id(path)
    loaded: list[LoadedTable] = []
    try:
        for worksheet in workbook.worksheets:
            max_row = worksheet.max_row or 1
            all_rows = [list(row) for row in worksheet.iter_rows(min_row=1, max_row=max_row, values_only=True)]
            detection = detect_header(all_rows)
            if detection is None or detection.confidence < 0.35:
                continue

            header_row_excel = detection.header_row_index + 1
            start, end = detection.start_column_index, detection.end_column_index
            header_cells = all_rows[detection.header_row_index]
            original_headers = ["" if value is None else str(value).strip() for value in header_cells[start : end + 1]]
            normalized = make_unique([normalize_column_name(name, i) for i, name in enumerate(original_headers)])
            last_data_excel = detection.last_data_row_index + 1 if detection.last_data_row_index is not None else max_row

            records: list[dict[str, object]] = []
            for excel_row, raw_row in enumerate(
                worksheet.iter_rows(min_row=header_row_excel + 1, max_row=last_data_excel, values_only=True),
                start=header_row_excel + 1,
            ):
                row = list(raw_row)[start : end + 1]
                if _is_blank_row(row) or _is_repeated_header(row, original_headers) or _is_total_row(row):
                    continue
                data_row_index = len(records) + 1
                record = dict(zip(normalized, row))
                record_no_col = normalized[0] if normalized and normalized[0] in {"no", "record_no"} else None
                record["_source_file_id"] = source_file_id
                record["_source_file_name"] = display_name
                record["_source_file"] = display_name
                record["_source_sheet"] = worksheet.title
                record["_source_excel_row"] = excel_row
                record["_source_header_row"] = header_row_excel
                record["_data_row_index"] = data_row_index
                record["_record_no"] = record.get(record_no_col) if record_no_col else data_row_index
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
                    if numeric_artifact and (almost_empty or df[col].isna().all()):
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
                        df["duration_reported_text"] = df[column].map(_cell_text)
                        df["duration_reported_seconds"] = df[column].map(parse_duration_seconds)
                        issues.append("Added parsed duration_reported_seconds")

            semantic_roles = {
                column: role
                for original, column in zip(original_headers, normalized)
                if (role := infer_semantic_role(column, original))
            }
            start_col = next((col for col, role in semantic_roles.items() if role == "start_time"), None)
            end_col = next((col for col, role in semantic_roles.items() if role == "end_time"), None)
            duration_col = next((col for col, role in semantic_roles.items() if role == "duration"), None)
            machine_col = next((col for col, role in semantic_roles.items() if role == "machine"), None)

            if not df.empty and "duration_reported_seconds" in df.columns:
                df["duration_calculated_seconds"] = df.apply(lambda row: _duration_calculated_seconds(row, start_col, end_col), axis=1)
                df["duration_difference_seconds"] = (df["duration_calculated_seconds"] - df["duration_reported_seconds"]).abs()
                df["duration_anomaly"] = df["duration_difference_seconds"] > 2
                df["duration_seconds"] = df["duration_reported_seconds"]
                if duration_col:
                    df[f"{duration_col}_seconds"] = df["duration_seconds"]
                    semantic_roles[f"{duration_col}_seconds"] = "duration_seconds"
                semantic_roles.update(
                    {
                        "duration_reported_seconds": "duration_reported_seconds",
                        "duration_calculated_seconds": "duration_calculated_seconds",
                        "duration_difference_seconds": "duration_difference_seconds",
                        "duration_seconds": "duration_seconds",
                    }
                )

            event_columns = [
                col
                for col in [
                    machine_col,
                    start_col,
                    end_col,
                    duration_col,
                    next((c for c, r in semantic_roles.items() if r == "loss_name"), None),
                    next((c for c, r in semantic_roles.items() if r == "loss_group"), None),
                    next((c for c, r in semantic_roles.items() if r == "loss_type"), None),
                ]
                if col and col in df.columns
            ]
            if not df.empty:
                _add_duplicate_flags(df, event_columns)
                overlap_count = _add_overlap_flags(df, machine_col, start_col, end_col)
            else:
                overlap_count = 0

            for technical in [
                "_source_file_id",
                "_source_file_name",
                "_source_sheet",
                "_source_excel_row",
                "_source_header_row",
                "_data_row_index",
                "_record_no",
            ]:
                if technical in df.columns:
                    semantic_roles[technical] = "provenance"

            effective_last_column = get_column_letter(start + len(original_headers))
            validation = {
                "header_row": header_row_excel,
                "first_data_row": header_row_excel + 1,
                "last_data_row": last_data_excel,
                "first_column": get_column_letter(start + 1),
                "last_column": effective_last_column,
                "duplicate_records": int(df["_is_exact_duplicate"].sum()) if "_is_exact_duplicate" in df.columns else 0,
                "overlap_pairs": overlap_count,
                "cross_midnight_records": int((df[start_col].dt.date != df[end_col].dt.date).sum()) if start_col and end_col and start_col in df.columns and end_col in df.columns else 0,
                "negative_intervals": int(((df[end_col] - df[start_col]).dt.total_seconds() < 0).sum()) if start_col and end_col and start_col in df.columns and end_col in df.columns else 0,
            }

            table_name = stable_table_name(path.name, worksheet.title)
            profile = SheetProfile(
            source_file=display_name,
                source_sheet=worksheet.title,
                table_name=table_name,
                header_row=header_row_excel,
                data_start_row=header_row_excel + 1,
                row_count=len(df),
                column_count=len(df.columns),
                last_data_row=last_data_excel,
                first_column=get_column_letter(start + 1),
                last_column=effective_last_column,
                header_confidence=detection.confidence,
                header_evidence=detection.evidence,
                original_columns=original_headers,
                normalized_columns=list(df.columns),
                column_mapping=dict(zip(original_headers, normalized)),
                semantic_roles=semantic_roles,
                issues=issues,
                validation=validation,
            )
            loaded.append(LoadedTable(profile=profile, dataframe=df))
        return loaded
    finally:
        workbook.close()


def profile_to_dict(profile: SheetProfile) -> dict:
    return asdict(profile)
