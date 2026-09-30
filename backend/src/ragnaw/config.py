from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ locally, /home/user/app in the Space image.
APP_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class LLMProvider:
    name: str
    base_url: str
    api_key: str
    model: str
    # Sent only when set: not every model accepts it (Groq's Llama models reject it).
    reasoning_effort: str = ""
    # Provider-specific request fields, e.g. Groq's reasoning_format for Qwen.
    extra_body: dict[str, Any] = field(default_factory=dict)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Providers retire models often; override via env instead of editing code.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_reasoning_effort: str = "low"
    # Groq rate limits are per model, so a second Groq model is a separate budget.
    # Empty disables it.
    groq_fallback_model: str = "qwen/qwen3.8-27b"
    groq_fallback_reasoning_effort: str = "none"
    # Qwen's default "raw" puts <think> in the answer and is rejected with tools.
    groq_fallback_reasoning_format: str = "hidden"
    gemini_api_key: str = ""
    # Flash-Lite: 15 requests/min, 1,000/day, 250K tokens/min on the free tier, against
    # 5/min and 20/day for gemini-3.8-flash. Faster in live tests too.
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_reasoning_effort: str = "low"
    llm_timeout_seconds: float = 30
    # Includes reasoning tokens, so leave headroom above the visible answer length.
    max_answer_tokens: int = 1000

    # Comma-separated so it can be set as a plain HF Space variable.
    cors_origins: str = "http://localhost:3000"

    max_question_chars: int = 500
    # Tool-calling rounds per question; one more call then forces a final answer.
    max_tool_rounds: int = 3
    # Tool output sent back to the model, ~1.5K tokens.
    max_tool_result_chars: int = 6000

    # `limits` syntax. Per visitor IP, and across everyone to protect the shared free quotas.
    chat_rate_limit: str = "6/minute;40/day"
    # Kept under provider capacity (~11 questions/min, ~585/day across Groq and Gemini),
    # so overflow gets a clean 429 instead of burning quota on calls that fail.
    chat_global_rate_limit: str = "10/minute;500/day"

    # Where ingest writes the SQLite DB, vector index and manifest.
    data_dir: Path = APP_ROOT / "data"
    # The Dockerfile downloads the embedding model here at build time.
    model_cache_dir: Path = APP_ROOT / ".cache" / "models"

    @property
    def cors_origin_list(self) -> list[str]:
        # Browsers send origins without a trailing slash; copying the URL from an address
        # bar adds one, and then nothing matches (seen on the first deploy).
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_providers(self) -> list[LLMProvider]:
        """Configured providers in fallback order: the next is tried when one returns 429.

        Groq's primary model goes first for speed, then a second Groq model with its own
        per-model limits, then Gemini Flash-Lite (15 requests/min, 1,000/day).
        All are called through their OpenAI-compatible APIs.
        """
        candidates = [
            LLMProvider(
                "groq",
                "https://api.groq.com/openai/v1",
                self.groq_api_key,
                self.groq_model,
                self.groq_reasoning_effort,
            ),
            LLMProvider(
                "groq-fallback",
                "https://api.groq.com/openai/v1",
                self.groq_api_key if self.groq_fallback_model else "",
                self.groq_fallback_model,
                self.groq_fallback_reasoning_effort,
                {"reasoning_format": self.groq_fallback_reasoning_format}
                if self.groq_fallback_reasoning_format
                else {},
            ),
            LLMProvider(
                "gemini",
                "https://generativelanguage.googleapis.com/v1beta/openai/",
                self.gemini_api_key,
                self.gemini_model,
                self.gemini_reasoning_effort,
            ),
        ]
        return [p for p in candidates if p.api_key]


@lru_cache
def get_settings() -> Settings:
    return Settings()
