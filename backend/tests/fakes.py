from dataclasses import dataclass, field

from ragnaw.llm import ProvidersUnavailable, Token, ToolCall, Turn


@dataclass
class Script:
    tokens: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)


class ScriptedRouter:
    """Stands in for LLMRouter: plays back one Script per round and records each call."""

    def __init__(self, *rounds: Script, unavailable: bool = False):
        self.rounds = list(rounds)
        self.unavailable = unavailable
        self.calls: list[dict] = []

    async def stream(self, messages, tools, tool_choice="auto", prefer=None):
        self.calls.append(
            {"messages": list(messages), "tool_choice": tool_choice, "prefer": prefer}
        )
        if self.unavailable:
            raise ProvidersUnavailable()
        script = self.rounds.pop(0)
        for text in script.tokens:
            yield Token(text)
        yield Turn("fake", "".join(script.tokens), script.tool_calls)
