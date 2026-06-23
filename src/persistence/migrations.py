from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    source_file_id TEXT,
    source_file_name TEXT,
    source_file_sha256 TEXT,
    source_catalog_version TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    execution_mode TEXT,
    query_plan_json TEXT,
    result_summary_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS conversation_states (
    conversation_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    summary TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS result_cache (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    parquet_path TEXT,
    row_count INTEGER,
    schema_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);
"""


def run_migrations(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_SQL)
    turn_columns = {row[1] for row in con.execute("PRAGMA table_info(conversation_turns)").fetchall()}
    if "response_json" not in turn_columns:
        con.execute("ALTER TABLE conversation_turns ADD COLUMN response_json TEXT")
    conversation_columns = {row[1] for row in con.execute("PRAGMA table_info(conversations)").fetchall()}
    for column in ["source_file_id", "source_file_name", "source_file_sha256", "source_catalog_version"]:
        if column not in conversation_columns:
            con.execute(f"ALTER TABLE conversations ADD COLUMN {column} TEXT")
    con.commit()
