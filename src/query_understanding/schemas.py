from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DetectionResult:
    value: Any = None
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    unresolved_terms: list[str] = field(default_factory=list)
