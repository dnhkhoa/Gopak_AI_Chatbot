from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


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
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
    ollama_num_ctx: int = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
    ollama_num_predict: int = int(os.getenv("OLLAMA_NUM_PREDICT", "384"))
    ollama_temperature: float = float(os.getenv("OLLAMA_TEMPERATURE", "0"))
    ollama_keep_alive: str = os.getenv("OLLAMA_KEEP_ALIVE", "-1")
    enable_heuristic_fallback: bool = os.getenv("ENABLE_HEURISTIC_FALLBACK", "false").lower() == "true"
    force_legacy_fallback_mode: bool = os.getenv("FORCE_LEGACY_FALLBACK_MODE", "false").lower() == "true"
    deterministic_confidence_threshold: float = float(os.getenv("DETERMINISTIC_CONFIDENCE_THRESHOLD", "0.90"))
    semantic_auto_accept_threshold: float = float(os.getenv("SEMANTIC_AUTO_ACCEPT_THRESHOLD", "0.90"))
    semantic_clarify_threshold: float = float(os.getenv("SEMANTIC_CLARIFY_THRESHOLD", "0.70"))
    enable_persistent_memory: bool = os.getenv("ENABLE_PERSISTENT_MEMORY", "true").lower() == "true"
    memory_db_path: Path = Path(os.getenv("MEMORY_DB_PATH", str(ROOT / "data" / "app_memory.db")))
    recent_turns_limit: int = int(os.getenv("RECENT_TURNS_LIMIT", "6"))
    result_cache_ttl_days: int = int(os.getenv("RESULT_CACHE_TTL_DAYS", "7"))


TARGET_EXCEL_FILES = (
    "EntryTransaction_20260203_164943.xlsx",
    "Loss_Assignment_20260203_100840.xlsx",
    "Machine_Downtime_20260203_100753.xlsx",
)


def get_settings() -> Settings:
    settings = Settings()
    settings.cache_dir.mkdir(exist_ok=True)
    settings.reports_dir.mkdir(exist_ok=True)
    settings.artifacts_dir.mkdir(exist_ok=True)
    settings.memory_db_path.parent.mkdir(exist_ok=True)
    return settings
