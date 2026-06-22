from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    text = text.lower().replace("đ", "d").replace("ð", "d").replace("Ä‘", "d")
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+", normalize_text(text))
