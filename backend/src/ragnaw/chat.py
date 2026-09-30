"""The question → tools → answer loop, as a stream of events for the SSE endpoint.

Events, in order: any number of `status` (one per tool call) and `token` (answer text),
then `sources`, then `done`. On failure, a single `error` replaces the rest.
"""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

import anyio.to_thread

from ragnaw.llm import ProvidersUnavailable, Token, Turn
from ragnaw.tools import ToolBox

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are RAGNaw. You answer questions about Pokémon using only your tools, which hold PokeAPI data for every Pokémon, form, move and ability as of the latest games.

Getting the facts:
- Call a tool for each part of the question. A named Pokémon: get_pokemon, even if misspelled. Lists filtered by type, ability, stats or generation: filter_pokemon with every filter the question mentions. Lore and descriptions: search_knowledge.
- If a tool returns an error, fix the call (e.g. use a suggested name) or say what failed.

Writing the answer:
- State only facts found in this conversation's tool results. Leave out anything they don't contain, even if you believe it: no move lists, dates, game mechanics or tips from memory.
- If the results don't answer the question, say so plainly.
- Only answer Pokémon questions; politely decline anything else.
- Be concise: a direct answer, then a short list or small table if it helps. Use Markdown. Don't mention tools or JSON."""

BUSY_MESSAGE = "RAGNaw is getting a lot of questions right now. Try again in a minute."
FAILED_MESSAGE = "Something went wrong while answering. Try again."


class Streamer(Protocol):
    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        prefer: str | None = None,
    ) -> AsyncIterator[Token | Turn]: ...


@dataclass(frozen=True)
class Event:
    name: str
    data: Any


def status_label(tool: str, arguments: str) -> str:
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        args = {}
    args = args if isinstance(args, dict) else {}
    name = args.get("name") or args.get("pokemon") or "/".join(args.get("types") or [])
    labels = {
        "search_knowledge": f"Searching the Pokédex for “{args.get('query', '')}”",
        "get_pokemon": f"Looking up {name}",
        "filter_pokemon": "Filtering Pokémon",
        "get_type_matchups": f"Checking type matchups for {name}",
        "get_evolution_chain": f"Tracing {name}'s evolution line",
        "get_move": f"Looking up the move {name}",
        "get_ability": f"Looking up the ability {name}",
    }
    return labels.get(tool, "Thinking")


def fit(data: dict, max_chars: int) -> str:
    """Serialize a tool result, dropping trailing list items until it fits the budget."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    while len(text) > max_chars and isinstance(data.get("results"), list) and data["results"]:
        data = {**data, "results": data["results"][:-1], "truncated": True}
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= max_chars else text[:max_chars] + "…(truncated)"


class Agent:
    def __init__(
        self,
        router: Streamer,
        tools: ToolBox,
        max_tool_rounds: int,
        max_tool_result_chars: int,
    ):
        self.router = router
        self.tools = tools
        self.max_tool_rounds = max_tool_rounds
        self.max_tool_result_chars = max_tool_result_chars

    async def answer(self, question: str) -> AsyncIterator[Event]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        sources: dict[str, dict] = {}
        provider: str | None = None

        try:
            for round_ in range(self.max_tool_rounds + 1):
                # The last round forbids tools, so the model has to answer with what it has.
                last = round_ == self.max_tool_rounds
                turn: Turn | None = None
                async for item in self.router.stream(
                    messages,
                    self.tools.specs,
                    tool_choice="none" if last else "auto",
                    prefer=provider,
                ):
                    if isinstance(item, Token):
                        yield Event("token", {"text": item.text})
                    else:
                        turn = item
                if turn is None:
                    raise RuntimeError("stream ended without a turn")
                provider = turn.provider

                # On the last round, ignore tool calls from a provider that made them anyway.
                if not turn.tool_calls or last:
                    if not turn.content:
                        raise RuntimeError("model returned no answer")
                    yield Event("sources", list(sources.values()))
                    done = {"provider": provider, "rounds": round_ + 1}
                    yield Event("done", {**done, "truncated": turn.truncated})
                    return

                messages.append(
                    {
                        "role": "assistant",
                        "content": turn.content or None,
                        "tool_calls": [c.as_message_part() for c in turn.tool_calls],
                    }
                )
                for call in turn.tool_calls:
                    yield Event("status", {"text": status_label(call.name, call.arguments)})
                    # Search embeds the query on CPU; keep it off the event loop.
                    result = await anyio.to_thread.run_sync(
                        self.tools.run, call.name, call.arguments
                    )
                    for source in result.sources:
                        sources.setdefault(source["url"], source)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": fit(result.data, self.max_tool_result_chars),
                        }
                    )
        except ProvidersUnavailable:
            yield Event("error", {"message": BUSY_MESSAGE})
        except Exception:  # the stream's last stop: report instead of cutting it off
            logger.exception("chat failed for question %r", question)
            yield Event("error", {"message": FAILED_MESSAGE})
