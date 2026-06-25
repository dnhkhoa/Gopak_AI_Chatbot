from __future__ import annotations

from enum import Enum


class LLMArchitectureMode(str, Enum):
    LEGACY_SINGLE_MODEL = "legacy_single_model"
    SPLIT_ROLES_SAME_MODEL = "split_roles_same_model"
    DUAL_MODEL = "dual_model"
