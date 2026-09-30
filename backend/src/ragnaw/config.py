from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Providers retire models often; override via env instead of editing code.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_reasoning_effort: str = "low"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
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
    chat_global_rate_limit: str = "30/minute;600/day"

    # Where ingest writes the SQLite DB, vector index and manifest.
    data_dir: Path = APP_ROOT / "data"
    # The Dockerfile downloads the embedding model here at build time.
    model_cache_dir: Path = APP_ROOT / ".cache" / "models"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_providers(self) -> list[LLMProvider]:
        """Configured providers in fallback order: the next is tried when one returns 429.

        Groq goes first for speed (8K tokens/min on the free plan); Gemini Flash has far more
        token headroom. Both are called through their OpenAI-compatible APIs.
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
