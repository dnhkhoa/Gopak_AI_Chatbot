from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata

from rapidfuzz import fuzz


ROLE_KEYWORDS = {
    "machine": ["máy", "may", "machine", "sx"],
    "duration_seconds": ["downtime", "dừng", "dung", "ngưng", "thời lượng", "duration", "dt"],
    "duration": ["downtime", "dừng", "dung", "ngưng", "thời lượng", "duration", "dt"],
    "start_time": ["ngày", "tháng", "tuần", "thời gian", "date", "time"],
    "end_time": ["ngày", "tháng", "tuần", "thời gian", "date", "time"],
    "loss_name": ["nguyên nhân", "tổn thất", "lỗi", "sự cố", "setup", "qc", "vật tư"],
    "loss_group": ["nhóm", "bảo trì", "sản xuất", "category"],
}


def normalize_text(text: str) -> str:
    text = text.lower().replace("đ", "d")
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def compact_catalog(catalog: dict) -> dict:
    return select_catalog_context(catalog, "", max_tables=3)


def select_catalog_context(catalog: dict, question: str, max_tables: int = 2) -> dict:
    q = normalize_text(question)
    scored = []
    for table in catalog.get("tables", []):
        source_text = normalize_text(f"{table['table_name']} {table.get('source', '')}")
        score = fuzz.partial_ratio(q, source_text) / 100 if q else 0
        for col in table.get("columns", []):
            if col["normalized_name"].startswith("_"):
                continue
            col_text = normalize_text(" ".join(str(x or "") for x in [col.get("normalized_name"), col.get("original_name"), col.get("description"), col.get("semantic_role")]))
            score += (fuzz.partial_ratio(q, col_text) / 100) * 0.7 if q else 0
            for sample in col.get("sample_values", [])[:8]:
                if sample and normalize_text(str(sample)) in q:
                    score += 2.0
        downtime_domain = any(term in q for term in ["downtime", "dung", "may", "ton that", "ton", "that", "bao tri", "nguyen nhan", "nguyen", "nhan", "qc", "dt"])
        entry_domain = any(term in q for term in ["cong", "truy cap", "xe", "can"])
        if downtime_domain:
            score += 6.0 if "machine_downtime" in table["table_name"] else 3.0 if "loss_assignment" in table["table_name"] else -2.0
        if any(term in q for term in ["nguyen nhan", "nguyen", "nhan", "ton that", "ton", "that", "bao tri", "setup", "qc"]):
            score += 4.0 if "machine_downtime" in table["table_name"] else 3.0 if "loss_assignment" in table["table_name"] else -4.0
        if downtime_domain and not entry_domain and "entrytransaction" in table["table_name"]:
            score -= 8.0
        if entry_domain:
            score += 3.0 if "entrytransaction" in table["table_name"] else 0
        scored.append((score, table))
    selected = [table for _, table in sorted(scored, key=lambda item: item[0], reverse=True)[:max_tables]]
    selected_names = {table["table_name"] for table in selected}

    tables = []
    for table in selected:
        columns = []
        for col in table.get("columns", []):
            name = col["normalized_name"]
            if name.startswith("_"):
                continue
            role = col.get("semantic_role")
            text = normalize_text(" ".join(str(x or "") for x in [name, col.get("original_name"), role, col.get("description")]))
            include = (
                role in {"machine", "duration", "duration_seconds", "start_time", "end_time", "loss_name", "loss_group", "loss_type"}
                or name in {"no"}
                or any(keyword in q and keyword in text for keyword in re.findall(r"\w+", q))
                or any(any(normalize_text(str(sample)) in q for sample in col.get("sample_values", [])[:8]) for _ in [0])
            )
            if include:
                columns.append(
                    {
                        "name": name,
                        "original": col.get("original_name"),
                        "dtype": col.get("dtype"),
                        "role": role,
                        "samples": [sample for sample in col.get("sample_values", [])[:6] if sample != ""],
                        "min": col.get("min"),
                        "max": col.get("max"),
                    }
                )
        tables.append({"table_name": table["table_name"], "source": table["source"], "row_count": table["row_count"], "columns": columns})
    rels = [
        rel for rel in catalog.get("relationships", [])
        if rel["left_table"] in selected_names and rel["right_table"] in selected_names
    ][:8]
    result = {
        "tables": tables,
        "relationships": rels,
        "schema_linking": {
            "selected_tables": list(selected_names),
            "omitted_tables": [table["table_name"] for table in catalog.get("tables", []) if table["table_name"] not in selected_names],
            "scores": {table["table_name"]: round(score, 3) for score, table in scored},
        },
    }
    log_planner_context_sample(question, result)
    return result


def log_planner_context_sample(question: str, context: dict) -> None:
    path = Path("artifacts/planner_context_samples.json")
    path.parent.mkdir(exist_ok=True)
    try:
        rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except json.JSONDecodeError:
        rows = []
    prompt_estimate = len(json.dumps(context, ensure_ascii=False)) // 4
    rows.append(
        {
            "question": question,
            "selected_tables": context["schema_linking"]["selected_tables"],
            "selected_columns": {
                table["table_name"]: [col["name"] for col in table.get("columns", [])]
                for table in context.get("tables", [])
            },
            "prompt_token_estimate": prompt_estimate,
            "omitted_tables": context["schema_linking"]["omitted_tables"],
            "schema_linking_score": context["schema_linking"]["scores"],
        }
    )
    path.write_text(json.dumps(rows[-200:], ensure_ascii=False, indent=2), encoding="utf-8")


def planner_messages(selected_catalog: dict, state: dict, question: str, validation_error: str | None = None, previous_response: str | None = None) -> list[dict]:
    system = (
        "You are a query planner. Return only a QueryPlan matching the JSON schema. "
        "Use only provided table, column, and categorical values. Do not invent SQL, numbers, columns, or values. "
        "count is different from sum. average means avg. top N requires dimension, metric, desc sort, and limit. "
        "If metric/time/group is ambiguous, intent=clarification. If data cannot answer the question, intent=refusal."
    )
    examples = [
        {"q": "Có bao nhiêu dòng?", "plan": {"intent": "query", "metrics": [{"aggregation": "count", "alias": "row_count"}], "output": "text"}},
        {"q": "Tổng downtime?", "plan": {"intent": "query", "metrics": [{"column": "duration_seconds", "aggregation": "sum", "alias": "total_duration_seconds"}], "output": "text"}},
        {"q": "Downtime trung bình?", "plan": {"intent": "query", "metrics": [{"column": "duration_seconds", "aggregation": "avg", "alias": "avg_duration_seconds"}], "output": "text"}},
        {"q": "Top 5 máy", "plan": {"intent": "query", "dimensions": ["machine"], "metrics": [{"column": "duration_seconds", "aggregation": "sum", "alias": "total_duration_seconds"}], "sort": [{"field": "total_duration_seconds", "direction": "desc"}], "limit": 5, "output": "table"}},
        {"q": "Theo ngày", "plan": {"intent": "chart", "dimensions": ["start_time"], "time_granularity": "day", "metrics": [{"column": "duration_seconds", "aggregation": "sum", "alias": "total_duration_seconds"}], "output": "line"}},
        {"q": "Máy nào tốt nhất?", "plan": {"intent": "clarification", "clarification_question": "Bạn muốn đánh giá tốt nhất theo downtime thấp, số lần dừng, hay chỉ số nào?"}},
        {"q": "Doanh thu năm 2024?", "plan": {"intent": "refusal", "clarification_question": "Dữ liệu hiện tại không có cột doanh thu để trả lời câu hỏi này."}},
    ]
    user_payload = {
        "question": question,
        "selected_catalog": selected_catalog,
        "conversation_state": state,
        "examples": examples,
    }
    if validation_error:
        user_payload["validation_errors"] = validation_error
        user_payload["previous_invalid_response"] = previous_response
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}]


def planner_prompt(catalog: dict, state: dict, question: str) -> str:
    return json.dumps({"question": question, "catalog": select_catalog_context(catalog, question), "state": state}, ensure_ascii=False)
