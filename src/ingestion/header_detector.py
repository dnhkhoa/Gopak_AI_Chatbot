from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class HeaderDetection:
    header_row_index: int
    start_column_index: int
    end_column_index: int
    score: float
    columns: list[str]


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def detect_header(rows: Sequence[Sequence[object]], min_columns: int = 2) -> HeaderDetection | None:
    best: HeaderDetection | None = None
    for idx, row in enumerate(rows):
        values = [_clean(v) for v in row]
        nonempty_positions = [i for i, value in enumerate(values) if value]
        if len(nonempty_positions) < min_columns:
            continue
        unique = len({values[i].lower() for i in nonempty_positions})
        text_like = sum(bool(re.search(r"[A-Za-zÀ-ỹ_]", values[i])) for i in nonempty_positions)
        next_density = 0
        for next_row in rows[idx + 1 : idx + 6]:
            next_density += sum(1 for v in next_row if _clean(v))
        score = len(nonempty_positions) * 2 + unique + text_like + min(next_density, len(nonempty_positions) * 5) * 0.2
        candidate = HeaderDetection(
            header_row_index=idx,
            start_column_index=min(nonempty_positions),
            end_column_index=max(nonempty_positions),
            score=score,
            columns=values[min(nonempty_positions) : max(nonempty_positions) + 1],
        )
        if best is None or candidate.score > best.score:
            best = candidate
    return best

