import json

import pytest
from fakes import Script, ScriptedRouter

from ragnaw.chat import BUSY_MESSAGE, Agent, fit
from ragnaw.llm import ToolCall
from ragnaw.rate_limit import RateLimiter


def lookup(name: str, call_id: str = "call_1") -> ToolCall:
    return ToolCall(call_id, "get_pokemon", json.dumps({"name": name}))


async def events(agent: Agent, question: str = "q") -> list:
    return [(e.name, e.data) async for e in agent.answer(question)]


@pytest.mark.anyio
async def test_runs_tools_then_streams_the_answer(tools):
    router = ScriptedRouter(
        Script(tool_calls=[lookup("pikachoo")]),
        Script(tokens=["Pikachu is ", "Electric."]),
    )
    result = await events(Agent(router, tools, max_tool_rounds=3, max_tool_result_chars=6000))

    assert [name for name, _ in result] == ["status", "token", "token", "sources", "done"]
    assert result[0][1] == {"text": "Looking up pikachoo"}
    assert result[3][1][0]["url"] == "https://pokeapi.co/api/v2/pokemon/pikachu"
    assert result[4][1] == {"provider": "fake", "rounds": 2, "truncated": False}

    # Round 2 saw the tool result, and stayed on the provider that answered round 1.
    tool_message = router.calls[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_1"
    assert json.loads(tool_message["content"])["name"] == "Pikachu"
    assert router.calls[1]["prefer"] == "fake"


@pytest.mark.anyio
async def test_last_round_forbids_tools(tools):
    router = ScriptedRouter(
        Script(tool_calls=[lookup("eevee")]),
        # Even if a provider ignores tool_choice="none", the loop ends with an answer.
        Script(tokens=["Eevee."], tool_calls=[lookup("eevee", "call_2")]),
    )
    result = await events(Agent(router, tools, max_tool_rounds=1, max_tool_result_chars=6000))
    assert [c["tool_choice"] for c in router.calls] == ["auto", "none"]
    assert result[-1] == ("done", {"provider": "fake", "rounds": 2, "truncated": False})


@pytest.mark.anyio
async def test_flags_answers_whose_stream_was_cut_off(tools):
    cut_off = Script(tokens=["Among standard species, **Talon"], finish_reason=None)
    result = await events(Agent(ScriptedRouter(cut_off), tools, 3, 6000))
    assert result[-1] == ("done", {"provider": "fake", "rounds": 1, "truncated": True})


@pytest.mark.anyio
async def test_reports_busy_when_no_provider_is_available(tools):
    agent = Agent(ScriptedRouter(unavailable=True), tools, 3, 6000)
    assert await events(agent) == [("error", {"message": BUSY_MESSAGE})]


@pytest.mark.anyio
async def test_empty_answer_is_an_error_not_a_blank_reply(tools):
    agent = Agent(ScriptedRouter(Script()), tools, 3, 6000)
    ((name, _),) = await events(agent)
    assert name == "error"


def test_fit_drops_results_before_cutting_text():
    data = {"total_matches": 50, "results": [{"name": "x" * 100}] * 50}
    text = fit(data, 1000)
    assert len(text) <= 1000
    parsed = json.loads(text)  # still valid JSON
    assert parsed["truncated"] is True
    assert 0 < len(parsed["results"]) < 50


def test_rate_limiter_counts_only_accepted_requests():
    limiter = RateLimiter("2/minute", "3/minute")
    assert limiter.hit("a") is None
    assert limiter.hit("a") is None
    assert limiter.hit("a") > 0  # per-client limit
    assert limiter.hit("b") is None  # the rejected request above used no global quota
    assert limiter.hit("c") > 0  # global limit (3) reached


def parse_sse(text: str) -> list[tuple[str, object]]:
    parsed = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields:
            parsed.append((fields["event"], json.loads(fields["data"])))
    return parsed


def test_chat_endpoint_streams_sse(client, tools, monkeypatch):
    router = ScriptedRouter(Script(tool_calls=[lookup("gengar")]), Script(tokens=["Boo."]))
    monkeypatch.setattr(client.app.state, "agent", Agent(router, tools, 3, 6000))
    monkeypatch.setattr(client.app.state, "rate_limiter", RateLimiter("10/minute", "10/minute"))

    res = client.post("/chat", json={"question": "Tell me about Gengar"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    assert [name for name, _ in parse_sse(res.text)] == ["status", "token", "sources", "done"]


def test_chat_endpoint_rejects_before_streaming(client, tools, monkeypatch):
    monkeypatch.setattr(client.app.state, "agent", Agent(ScriptedRouter(), tools, 3, 6000))
    monkeypatch.setattr(client.app.state, "rate_limiter", RateLimiter("1/minute", "10/minute"))

    assert client.post("/chat", json={"question": "   "}).status_code == 422
    assert client.post("/chat", json={"question": "x" * 501}).status_code == 422

    # The rejected questions didn't use the one-per-minute allowance...
    router = ScriptedRouter(Script(tokens=["ok"]))
    monkeypatch.setattr(client.app.state, "agent", Agent(router, tools, 3, 6000))
    assert client.post("/chat", json={"question": "hi"}).status_code == 200
    # ...but this one is over it.
    res = client.post("/chat", json={"question": "hi again"})
    assert res.status_code == 429
    assert int(res.headers["retry-after"]) > 0


def test_chat_endpoint_without_llm_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(client.app.state, "agent", None)
    assert client.post("/chat", json={"question": "hi"}).status_code == 503
