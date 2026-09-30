import httpx
import openai
import pytest
from openai.types.chat import ChatCompletionChunk

from ragnaw.config import LLMProvider
from ragnaw.llm import LLMRouter, ProvidersUnavailable, Token, Turn

GROQ = LLMProvider("groq", "https://groq.example/v1", "k", "m", "low")
GEMINI = LLMProvider("gemini", "https://gemini.example/v1", "k", "m")


def chunk(delta: dict) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(
        {
            "id": "c",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "m",
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
    )


def rate_limited(retry_after: str | None = None) -> openai.RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(429, headers=headers, request=httpx.Request("POST", "http://x"))
    return openai.RateLimitError("rate limited", response=response, body=None)


class FakeClient:
    """Mimics AsyncOpenAI().chat.completions.create(stream=True)."""

    def __init__(self, chunks=(), error: Exception | None = None):
        self.chunks, self.error, self.requests = list(chunks), error, []
        self.chat = self
        self.completions = self

    async def create(self, **params):
        self.requests.append(params)
        if self.error:
            raise self.error

        async def stream():
            for c in self.chunks:
                yield c

        return stream()


def make_router(**clients: FakeClient) -> LLMRouter:
    providers = [p for p in (GROQ, GEMINI) if p.name in clients]
    router = LLMRouter(providers, timeout=5, max_tokens=100)
    router.clients = clients
    return router


async def collect(router: LLMRouter, **kwargs) -> tuple[list[str], Turn]:
    tokens, turn = [], None
    async for item in router.stream([{"role": "user", "content": "hi"}], [], **kwargs):
        if isinstance(item, Token):
            tokens.append(item.text)
        else:
            turn = item
    return tokens, turn


@pytest.mark.anyio
async def test_streams_tokens_and_reassembles_fragmented_tool_calls():
    first_part = {
        "index": 0,
        "id": "call_a",
        "type": "function",
        "function": {"name": "get_pokemon", "arguments": '{"na'},
        # e.g. Gemini's thought signature: must survive the round trip unchanged
        "extra_content": {"google": {"thought_signature": "sig"}},
    }
    second_part = {"index": 0, "function": {"arguments": 'me": "pikachu"}'}}
    groq = FakeClient(
        [
            chunk({"content": "Let me "}),
            chunk({"content": "check."}),
            chunk({"tool_calls": [first_part]}),
            chunk({"tool_calls": [second_part]}),
        ]
    )
    tokens, turn = await collect(make_router(groq=groq))

    assert tokens == ["Let me ", "check."]
    assert turn.provider == "groq"
    (call,) = turn.tool_calls
    assert (call.id, call.name, call.arguments) == ("call_a", "get_pokemon", '{"name": "pikachu"}')
    assert call.as_message_part()["extra_content"] == {"google": {"thought_signature": "sig"}}
    assert groq.requests[0]["reasoning_effort"] == "low"
    # Truncates Gemini streams after one chunk.
    assert "stream_options" not in groq.requests[0]


@pytest.mark.anyio
async def test_omits_reasoning_effort_when_unset():
    gemini = FakeClient([chunk({"content": "hi"})])
    await collect(make_router(gemini=gemini))
    assert "reasoning_effort" not in gemini.requests[0]


@pytest.mark.anyio
async def test_falls_back_on_429_and_skips_the_provider_while_cooling_down():
    groq = FakeClient(error=rate_limited(retry_after="60"))
    gemini = FakeClient([chunk({"content": "hi"})])
    router = make_router(groq=groq, gemini=gemini)

    _, turn = await collect(router)
    assert turn.provider == "gemini"

    await collect(router)
    assert len(groq.requests) == 1  # not retried during the Retry-After window
    assert len(gemini.requests) == 2


@pytest.mark.anyio
async def test_prefers_the_provider_that_started_the_request():
    groq = FakeClient([chunk({"content": "a"})])
    gemini = FakeClient([chunk({"content": "b"})])
    _, turn = await collect(make_router(groq=groq, gemini=gemini), prefer="gemini")
    assert turn.provider == "gemini"
    assert not groq.requests


@pytest.mark.anyio
async def test_raises_when_every_provider_is_unavailable():
    router = make_router(
        groq=FakeClient(error=rate_limited()), gemini=FakeClient(error=rate_limited())
    )
    with pytest.raises(ProvidersUnavailable):
        await collect(router)


@pytest.mark.anyio
async def test_does_not_fall_back_on_client_errors():
    response = httpx.Response(400, request=httpx.Request("POST", "http://x"))
    bad_request = openai.BadRequestError("bad schema", response=response, body=None)
    gemini = FakeClient([chunk({"content": "hi"})])
    with pytest.raises(openai.BadRequestError):
        await collect(make_router(groq=FakeClient(error=bad_request), gemini=gemini))
    assert not gemini.requests


def test_reads_retry_delay_from_gemini_error_body():
    response = httpx.Response(429, request=httpx.Request("POST", "http://x"))
    body = [{"error": {"details": [{"@type": "RetryInfo", "retryDelay": "45s"}]}}]
    error = openai.RateLimitError(
        "Quota exceeded. Please retry in 45.05s.", response=response, body=body
    )
    assert LLMRouter._retry_after(error) == 45
    assert LLMRouter._retry_after(rate_limited(retry_after="7")) == 7
    assert LLMRouter._retry_after(rate_limited()) == 20

