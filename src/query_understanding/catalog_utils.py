from __future__ import annotations

from typing import Any


def find_table(catalog: dict, prefix: str) -> dict | None:
    return next((table for table in catalog.get("tables", []) if table["table_name"].startswith(prefix)), None)


def role_column(table: dict, role: str) -> str | None:
    for col in table.get("columns", []):
        if col.get("semantic_role") == role:
            return col["normalized_name"]
    return None


def column_info(table: dict, column: str) -> dict[str, Any] | None:
    return next((col for col in table.get("columns", []) if col["normalized_name"] == column), None)


def business_columns(table: dict) -> list[str]:
    return [col["normalized_name"] for col in table.get("columns", []) if not col["normalized_name"].startswith("_")]
