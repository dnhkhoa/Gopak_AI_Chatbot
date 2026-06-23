from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    lowered = (
        str(text)
        .lower()
        .replace("đ", "d")
        .replace("Đ", "d")
        .replace("Ä‘", "d")
        .replace("Ã°", "d")
        .replace("Ã„â€˜", "d")
    )
    normalized = unicodedata.normalize("NFKD", lowered)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+", normalize_text(text))
