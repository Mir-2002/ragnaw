"""The tools the LLM can call, their OpenAI-format specs, and dispatch.

Specs are generated from the Pydantic argument models, then flattened: no titles, no
$refs, no nullable anyOf. That keeps them small (they're resent every tool round against
Groq's 8K tokens/minute) and inside the JSON Schema subset Gemini's OpenAI endpoint
accepts. Errors come back as {"error": ...} so the model can correct itself.

Bounds (maximum, maxItems, ...) are left out of the specs on purpose: Groq validates tool
calls against the schema server-side and fails the whole response on a violation (seen
live: limit=50 against maximum 25), so the model never gets to correct itself. Pydantic
still enforces them here, where an error can be fed back.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from ragnaw.catalog import SORTABLE, Catalog, ResolutionError
from ragnaw.retrieval import KnowledgeIndex

SEARCH_RESULTS = 5
MAX_FILTER_RESULTS = 25
# Kept out of specs; see module docstring.
SERVER_SIDE_ONLY = {"maximum", "minimum", "maxItems", "minItems", "maxLength", "minLength"}
POKEAPI = "https://pokeapi.co/api/v2"

Stat = Literal[SORTABLE]


class SearchKnowledge(BaseModel):
    """Search Pokédex entries, move effects and ability descriptions by meaning. Use for
    lore, behavior and descriptions. For a named Pokémon's data use get_pokemon."""

    query: str
    kind: Literal["species", "move", "ability"] | None = Field(
        None, description="Restrict to one kind of document"
    )


class GetPokemon(BaseModel):
    """Types, base stats, abilities, forms and a Pokédex entry for one Pokémon or form
    (e.g. "Pikachu", "Mega Charizard X", "Alolan Raichu")."""

    name: str


class StatCondition(BaseModel):
    stat: Stat
    op: Literal[">=", "<=", "="]
    value: int = Field(ge=0, le=1000)


class FilterPokemon(BaseModel):
    """Find and rank Pokémon by type, ability, base stats, generation or legendary status,
    e.g. "fastest Fire types" or "Gen 4 Pokémon with Levitate"."""

    types: list[str] = Field([], max_length=2, description="Must have all of these types")
    ability: str | None = None
    conditions: list[StatCondition] = Field([], max_length=6)
    generation: int | None = Field(None, ge=1, le=9)
    legendary: bool | None = Field(None, description="True: only legendary/mythical")
    include_forms: bool = Field(False, description="Include Megas and other forms")
    sort_by: Stat = "base_stat_total"
    descending: bool = True
    limit: int = Field(10, description=f"1-{MAX_FILTER_RESULTS}")

    @field_validator("limit")
    @classmethod
    def clamp_limit(cls, value: int) -> int:
        # Asking for too many rows isn't worth an error round trip.
        return min(max(value, 1), MAX_FILTER_RESULTS)


class GetTypeMatchups(BaseModel):
    """Damage multipliers taken from each attacking type, and what the types hit
    super-effectively. Give a Pokémon name or one or two types."""

    pokemon: str | None = None
    types: list[str] = Field([], max_length=2)


class GetEvolutionChain(BaseModel):
    """Every member of a Pokémon's evolution family and how each evolution happens."""

    name: str


class GetMove(BaseModel):
    """Type, category, power, accuracy, PP, priority and effect of a move."""

    name: str


class GetAbility(BaseModel):
    """What an ability does and which Pokémon have it. To narrow those Pokémon by
    generation, type or stats, use filter_pokemon with the ability instead."""

    name: str


def _flatten(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(defs[node["$ref"].split("/")[-1]])
        variants = node.get("anyOf")
        if variants and any(v.get("type") == "null" for v in variants):
            (kept,) = [v for v in variants if v.get("type") != "null"]
            node = {**{k: v for k, v in node.items() if k != "anyOf"}, **kept}
        return {
            k: walk(v)
            for k, v in node.items()
            if k != "title" and k not in SERVER_SIDE_ONLY and not (k == "default" and v is None)
        }

    return walk(schema)


def _spec(name: str, model: type[BaseModel]) -> dict[str, Any]:
    schema = _flatten(model.model_json_schema())
    description = " ".join((model.__doc__ or "").split())
    schema.pop("description", None)
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": schema},
    }


@dataclass
class ToolResult:
    data: dict
    # For the UI's source cards; never sent to the model.
    sources: list[dict] = field(default_factory=list)


class ToolBox:
    def __init__(self, catalog: Catalog, index: KnowledgeIndex):
        self.catalog = catalog
        self.index = index
        self.handlers: dict[str, tuple[type[BaseModel], Callable[[Any], ToolResult]]] = {
            "search_knowledge": (SearchKnowledge, self._search),
            "get_pokemon": (GetPokemon, self._pokemon),
            "filter_pokemon": (FilterPokemon, self._filter),
            "get_type_matchups": (
                GetTypeMatchups,
                lambda a: ToolResult(catalog.type_matchups(a.types, a.pokemon)),
            ),
            "get_evolution_chain": (
                GetEvolutionChain,
                lambda a: ToolResult(catalog.evolution_chain(a.name)),
            ),
            "get_move": (GetMove, lambda a: self._linked(catalog.get_move(a.name), "move")),
            "get_ability": (
                GetAbility,
                lambda a: self._linked(catalog.get_ability(a.name), "ability"),
            ),
        }
        self.specs = [_spec(name, model) for name, (model, _) in self.handlers.items()]

    def run(self, name: str, arguments: str) -> ToolResult:
        if name not in self.handlers:
            available = ", ".join(self.handlers)
            return ToolResult({"error": f"Unknown tool '{name}'. Available: {available}."})
        model, handler = self.handlers[name]
        try:
            args = model.model_validate_json(arguments or "{}")
        except ValidationError as e:
            problems = "; ".join(
                f"{'.'.join(map(str, err['loc'])) or 'arguments'}: {err['msg']}"
                for err in e.errors()
            )
            return ToolResult({"error": f"Invalid arguments for {name}: {problems}"})
        try:
            return handler(args)
        except ResolutionError as e:
            return ToolResult({"error": str(e)})

    def _search(self, args: SearchKnowledge) -> ToolResult:
        kinds = {args.kind} if args.kind else None
        hits = self.index.search(args.query, k=SEARCH_RESULTS, kinds=kinds)
        return ToolResult(
            {
                "results": [
                    {"title": h.doc["title"], "kind": h.doc["kind"], "text": h.doc["text"]}
                    for h in hits
                ]
            },
            [{"title": h.doc["title"], "kind": h.doc["kind"], "url": h.doc["url"]} for h in hits],
        )

    def _pokemon(self, args: GetPokemon) -> ToolResult:
        data = self.catalog.get_pokemon(args.name)
        source = {
            "title": data["name"],
            "kind": "pokemon",
            "url": f"{POKEAPI}/pokemon/{data.pop('identifier')}",
            "image": data.pop("sprite_url"),
        }
        return ToolResult(data, [source])

    @staticmethod
    def _linked(data: dict, kind: str) -> ToolResult:
        url = f"{POKEAPI}/{kind}/{data.pop('identifier')}"
        return ToolResult(data, [{"title": data["name"], "kind": kind, "url": url}])

    def _filter(self, args: FilterPokemon) -> ToolResult:
        return ToolResult(
            self.catalog.filter_pokemon(
                types=args.types,
                ability=args.ability,
                conditions=[(c.stat, c.op, c.value) for c in args.conditions],
                generation=args.generation,
                legendary=args.legendary,
                include_forms=args.include_forms,
                sort_by=args.sort_by,
                descending=args.descending,
                limit=args.limit,
            )
        )


def spec_tokens_estimate(specs: list[dict]) -> int:
    """Rough size of the specs as sent (~4 characters per token)."""
    return len(json.dumps(specs, separators=(",", ":"))) // 4
