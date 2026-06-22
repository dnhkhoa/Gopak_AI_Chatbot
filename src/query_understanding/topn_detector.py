from __future__ import annotations

import re

from src.query_understanding.schemas import DetectionResult
from src.query_understanding.text import normalize_text


def detect_topn(question: str) -> DetectionResult:
    q = normalize_text(question)
    direction = "asc" if any(term in q for term in ["bottom", "thap nhat", "nho nhat", "it nhat"]) and "downtime nho nhat" not in q else "desc"
    match = re.search(r"\btop\s*(\d+)\b", q)
    if match:
        return DetectionResult({"limit": int(match.group(1)), "direction": direction}, 0.96, ["explicit top N"])
    if "top" in q:
        return DetectionResult({"limit": 20, "direction": direction}, 0.90, ["top ranking"])
    if "bottom" in q:
        match = re.search(r"\bbottom\s*(\d+)\b", q)
        return DetectionResult({"limit": int(match.group(1)) if match else 5, "direction": "asc"}, 0.94, ["bottom N"])
    if any(term in q for term in ["cao nhat", "nhieu nhat", "lon nhat", "dung dau"]):
        return DetectionResult({"limit": 1, "direction": "desc"}, 0.85, ["ranking superlative"])
    if any(term in q for term in ["thap nhat", "it nhat"]):
        return DetectionResult({"limit": 1, "direction": "asc"}, 0.85, ["bottom superlative"])
    return DetectionResult(None, 0.0)
