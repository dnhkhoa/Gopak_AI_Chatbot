from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import os

from src.llm.architecture import LLMArchitectureMode


ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    cache_dir: Path = ROOT / "cache"
    reports_dir: Path = ROOT / "reports"
    artifacts_dir: Path = ROOT / "artifacts"
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen3.5:9b"))
    ollama_num_ctx: int = field(default_factory=lambda: int(os.getenv("OLLAMA_NUM_CTX", "4096")))
    ollama_num_predict: int = field(default_factory=lambda: int(os.getenv("OLLAMA_NUM_PREDICT", "384")))
    ollama_temperature: float = field(default_factory=lambda: float(os.getenv("OLLAMA_TEMPERATURE", "0")))
    ollama_keep_alive: str = field(default_factory=lambda: os.getenv("OLLAMA_KEEP_ALIVE", "-1"))
    llm_architecture_mode: LLMArchitectureMode = field(
        default_factory=lambda: LLMArchitectureMode(os.getenv("LLM_ARCHITECTURE_MODE", LLMArchitectureMode.LEGACY_SINGLE_MODEL.value))
    )
    fast_structured_model: str = field(default_factory=lambda: os.getenv("FAST_STRUCTURED_MODEL", ""))
    grounded_composer_model: str = field(default_factory=lambda: os.getenv("GROUNDED_COMPOSER_MODEL", os.getenv("OLLAMA_MODEL", "qwen3.5:9b")))
    embedding_model_enabled: bool = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL_ENABLED", "false").lower() == "true")
    enable_heuristic_fallback: bool = field(default_factory=lambda: os.getenv("ENABLE_HEURISTIC_FALLBACK", "false").lower() == "true")
    force_legacy_fallback_mode: bool = field(default_factory=lambda: os.getenv("FORCE_LEGACY_FALLBACK_MODE", "false").lower() == "true")
    deterministic_confidence_threshold: float = field(default_factory=lambda: float(os.getenv("DETERMINISTIC_CONFIDENCE_THRESHOLD", "0.90")))
    semantic_auto_accept_threshold: float = field(default_factory=lambda: float(os.getenv("SEMANTIC_AUTO_ACCEPT_THRESHOLD", "0.90")))
    semantic_clarify_threshold: float = field(default_factory=lambda: float(os.getenv("SEMANTIC_CLARIFY_THRESHOLD", "0.70")))
    enable_persistent_memory: bool = field(default_factory=lambda: os.getenv("ENABLE_PERSISTENT_MEMORY", "true").lower() == "true")
    memory_db_path: Path = field(default_factory=lambda: Path(os.getenv("MEMORY_DB_PATH", str(ROOT / "data" / "app_memory.db"))))
    recent_turns_limit: int = field(default_factory=lambda: int(os.getenv("RECENT_TURNS_LIMIT", "6")))
    result_cache_ttl_days: int = field(default_factory=lambda: int(os.getenv("RESULT_CACHE_TTL_DAYS", "7")))
    show_internal_debug_metadata: bool = field(default_factory=lambda: os.getenv("SHOW_INTERNAL_DEBUG_METADATA", "false").lower() == "true")
    customer_production_mode: bool = field(default_factory=lambda: os.getenv("CUSTOMER_PRODUCTION_MODE", "true").lower() == "true")
    customer_upload_enabled: bool = field(default_factory=lambda: os.getenv("CUSTOMER_UPLOAD_ENABLED", "false").lower() == "true")
    business_timezone: str = field(default_factory=lambda: os.getenv("BUSINESS_TIMEZONE", ""))
    performance_formula_mode: str = field(default_factory=lambda: os.getenv("PERFORMANCE_FORMULA_MODE", "disabled"))
    ideal_cycle_time_ms: float | None = field(default_factory=lambda: float(os.getenv("IDEAL_CYCLE_TIME_MS")) if os.getenv("IDEAL_CYCLE_TIME_MS") else None)
    standard_rate_per_hour: float | None = field(default_factory=lambda: float(os.getenv("STANDARD_RATE_PER_HOUR")) if os.getenv("STANDARD_RATE_PER_HOUR") else None)
    query_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("QUERY_TIMEOUT_SECONDS", "30")))
    query_memory_limit: str = field(default_factory=lambda: os.getenv("QUERY_MEMORY_LIMIT", "512MB"))
    max_result_rows: int = field(default_factory=lambda: int(os.getenv("MAX_RESULT_ROWS", "500")))


SOURCE_REGISTRY_PATH = ROOT / "config" / "source_registry.json"


def _target_excel_files() -> tuple[str, ...]:
    if not SOURCE_REGISTRY_PATH.exists():
        return ("Machine_Downtime_20260203_100753.xlsx", "Loss_Assignment_20260203_100840.xlsx", "Cup3.xlsx")
    payload = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    sources = payload.get("sources", [])
    return tuple(str(item["workbook_path"]) for item in sources)


TARGET_EXCEL_FILES = _target_excel_files()


def get_settings() -> Settings:
    settings = Settings()
    settings.cache_dir.mkdir(exist_ok=True)
    settings.reports_dir.mkdir(exist_ok=True)
    settings.artifacts_dir.mkdir(exist_ok=True)
    settings.memory_db_path.parent.mkdir(exist_ok=True)
    return settings
