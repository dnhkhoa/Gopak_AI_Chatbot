from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from time import perf_counter
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.config import Settings


@dataclass
class LLMResponse:
    text: str
    latency_ms: float


class OllamaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def health(self) -> dict:
        base = self.settings.ollama_base_url.rstrip("/")
        try:
            with urlopen(f"{base}/api/tags", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [item.get("name") for item in payload.get("models", [])]
            return {"ok": True, "models": models, "model_available": self.settings.ollama_model in models}
        except Exception as exc:
            return {"ok": False, "models": [], "model_available": False, "error": str(exc)}

    def cli_models(self) -> list[str]:
        try:
            result = subprocess.run(["ollama", "list"], check=False, capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            return []
        lines = [line.split()[0] for line in result.stdout.splitlines()[1:] if line.strip()]
        return lines

    def generate(self, prompt: str) -> LLMResponse:
        base = self.settings.ollama_base_url.rstrip("/")
        body = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": self._keep_alive_value(),
            "options": {
                "temperature": self.settings.ollama_temperature,
                "num_ctx": self.settings.ollama_num_ctx,
                "num_predict": self.settings.ollama_num_predict,
            },
        }
        request = Request(
            f"{base}/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = perf_counter()
        try:
            with urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"Ollama is not reachable at {base}: {exc}") from exc
        return LLMResponse(text=payload.get("response", ""), latency_ms=(perf_counter() - start) * 1000)

    def chat(self, messages: list[dict], format_schema: dict | None = None) -> LLMResponse:
        base = self.settings.ollama_base_url.rstrip("/")
        body = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": self._keep_alive_value(),
            "options": {
                "temperature": self.settings.ollama_temperature,
                "num_ctx": self.settings.ollama_num_ctx,
                "num_predict": self.settings.ollama_num_predict,
                "seed": 42,
            },
        }
        if format_schema is not None:
            body["format"] = format_schema
        request = Request(
            f"{base}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = perf_counter()
        try:
            with urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"Ollama chat is not reachable at {base}: {exc}") from exc
        content = payload.get("message", {}).get("content", "")
        return LLMResponse(text=content, latency_ms=(perf_counter() - start) * 1000)

    def _keep_alive_value(self) -> int | str:
        value = self.settings.ollama_keep_alive.strip()
        try:
            return int(value)
        except ValueError:
            return value
