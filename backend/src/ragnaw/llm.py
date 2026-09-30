"""Streaming chat completions across providers, with fallback on rate limits and outages.

A provider that returns 429 (or is unreachable) is skipped for its Retry-After period, so
while Groq's per-minute budget is spent, requests go straight to Gemini instead of paying
a failed round trip first. Fallback only happens before the first token is streamed.
"""

import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import openai
from openai import AsyncOpenAI

from ragnaw.config import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_SECONDS = 20
MAX_COOLDOWN_SECONDS = 120
# Gemini puts the wait in the error body ("retryDelay": "45s", "Please retry in 45.05s")
# rather than a Retry-After header.
RETRY_IN_BODY = re.compile(r"(?:retryDelay['\"]?\s*:\s*['\"]|retry in )(\d+(?:\.\d+)?)s")

# Worth trying the next provider for; anything else (e.g. a 400) is a bug to surface.
RETRYABLE = (
    openai.RateLimitError,
    openai.APIConnectionError,  # includes APITimeoutError
    openai.InternalServerError,
)


class ProvidersUnavailable(Exception):
    """Every configured provider is rate-limited or down."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str
    # Provider-specific fields (e.g. Gemini thought signatures) that must be sent back
    # unchanged with the tool result.
    extra: dict[str, Any] = field(default_factory=dict)

    def as_message_part(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
            **self.extra,
        }


@dataclass
class Turn:
    provider: str
    content: str
    tool_calls: list[ToolCall]
    # None means the stream ended without one: Gemini sometimes cuts streams short.
    finish_reason: str | None = None

    @property
    def truncated(self) -> bool:
        return self.finish_reason in (None, "length")


@dataclass
class Token:
    text: str


class LLMRouter:
    def __init__(self, providers: list[LLMProvider], timeout: float, max_tokens: int):
        self.providers = providers
        self.max_tokens = max_tokens
        self.clients = {
            p.name: AsyncOpenAI(api_key=p.api_key, base_url=p.base_url, timeout=timeout)
            for p in providers
        }
        self.cooldown_until: dict[str, float] = {}

    def _order(self, prefer: str | None) -> list[LLMProvider]:
        now = time.monotonic()
        ready = [p for p in self.providers if self.cooldown_until.get(p.name, 0) <= now]
        # Keep a request on one provider across rounds where possible, so tool-call
        # history carries that provider's own metadata.
        return sorted(ready, key=lambda p: p.name != prefer)

    @staticmethod
    def _retry_after(error: Exception) -> float:
        response = getattr(error, "response", None)
        header = response.headers.get("retry-after") if response is not None else None
        if header:
            try:
                return float(header)
            except ValueError:
                pass
        match = RETRY_IN_BODY.search(f"{getattr(error, 'body', '')} {error}")
        return float(match.group(1)) if match else DEFAULT_COOLDOWN_SECONDS

    def _cool_down(self, provider: LLMProvider, error: Exception) -> None:
        seconds = min(max(self._retry_after(error), 1), MAX_COOLDOWN_SECONDS)
        self.cooldown_until[provider.name] = time.monotonic() + seconds
        logger.warning("%s unavailable (%s); skipping for %.0fs", provider.name, error, seconds)

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        prefer: str | None = None,
    ) -> AsyncIterator[Token | Turn]:
        """Yield Tokens as the answer streams, then one Turn with the full result."""
        for provider in self._order(prefer):
            started = False
            try:
                params: dict[str, Any] = {
                    "model": provider.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": tool_choice,
                    "max_tokens": self.max_tokens,
                    # No stream_options={"include_usage": True}: on Gemini's OpenAI
                    # endpoint it ends the stream after the first chunk (seen live).
                    "stream": True,
                }
                if provider.reasoning_effort:
                    params["reasoning_effort"] = provider.reasoning_effort
                if provider.extra_body:
                    params["extra_body"] = provider.extra_body
                stream = await self.clients[provider.name].chat.completions.create(**params)

                content: list[str] = []
                calls: dict[int, ToolCall] = {}
                finish_reason = None
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    finish_reason = chunk.choices[0].finish_reason or finish_reason
                    delta = chunk.choices[0].delta
                    if delta.content:
                        started = True
                        content.append(delta.content)
                        yield Token(delta.content)
                    for part in delta.tool_calls or []:
                        index = part.index if part.index is not None else len(calls)
                        call = calls.setdefault(index, ToolCall("", "", ""))
                        if part.id:
                            call.id = part.id
                        if part.function and part.function.name:
                            call.name = part.function.name
                        if part.function and part.function.arguments:
                            call.arguments += part.function.arguments
                        call.extra.update(part.model_extra or {})

                tool_calls = [calls[i] for i in sorted(calls)]
                for n, call in enumerate(tool_calls):
                    call.id = call.id or f"call_{n}"
                turn = Turn(provider.name, "".join(content), tool_calls, finish_reason)
                if turn.truncated:
                    logger.warning("%s stream ended early (%s)", provider.name, finish_reason)
                yield turn
                return
            except RETRYABLE as e:
                if started:
                    raise
                self._cool_down(provider, e)
        raise ProvidersUnavailable()
