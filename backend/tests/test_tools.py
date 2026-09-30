import json

import pytest

from ragnaw.tools import spec_tokens_estimate


def run(tools, tool, **args):
    return tools.run(tool, json.dumps(args))


def test_specs_stay_small_and_flat(tools):
    # Resent every tool round against Groq's 8K tokens/minute.
    assert spec_tokens_estimate(tools.specs) < 1000
    text = json.dumps(tools.specs)
    for unsupported in ('"$ref"', '"$defs"', '"anyOf"', '"title"'):
        assert unsupported not in text


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("pikachoo", "Pikachu"),
        ("mr mime", "Mr. Mime"),
        ("alolan raichu", "Alolan Raichu"),
        ("charizard-mega-x", "Mega Charizard X"),
    ],
)
def test_get_pokemon_resolves_names(tools, query, expected):
    assert run(tools, "get_pokemon", name=query)["name"] == expected


def test_ambiguous_name_asks_instead_of_guessing(tools):
    error = run(tools, "get_pokemon", name="mega charizard")["error"]
    assert "Mega Charizard X" in error and "Mega Charizard Y" in error


def test_filter_sorts_and_filters(tools):
    result = run(tools, "filter_pokemon", types=["fire"], sort_by="speed", limit=5)
    speeds = [r["speed"] for r in result["results"]]
    assert speeds == sorted(speeds, reverse=True)
    assert all("Fire" in r["types"] for r in result["results"])
    assert result["total_matches"] > 5


def test_filter_by_ability_and_stat_condition(tools):
    result = run(
        tools,
        "filter_pokemon",
        types=["dragon"],
        conditions=[{"stat": "attack", "op": ">=", "value": 130}],
        legendary=False,
    )
    names = {r["name"] for r in result["results"]}
    assert {"Dragonite", "Garchomp", "Salamence"} <= names
    assert all(r["attack"] >= 130 for r in result["results"])

    levitate = run(tools, "filter_pokemon", ability="levitate", generation=4)
    assert "Bronzong" in {r["name"] for r in levitate["results"]}


def test_dual_type_matchups(tools):
    taken = run(tools, "get_type_matchups", types=["Water", "Ground"])["damage_taken"]
    assert taken["4x"] == ["Grass"]
    assert taken["immune"] == ["Electric"]

    gengar = run(tools, "get_type_matchups", pokemon="gengar")
    assert gengar["defending_types"] == "Ghost/Poison"
    assert set(gengar["damage_taken"]["immune"]) == {"Normal", "Fighting"}


def test_evolution_chain(tools):
    chain = run(tools, "get_evolution_chain", name="raichu")
    assert chain["members"] == ["Pichu", "Pikachu", "Raichu"]
    assert {
        "from": "Pikachu",
        "to": "Alolan Raichu",
        "methods": ["use Thunder Stone in Alola"],
    } in (chain["evolutions"])
    assert run(tools, "get_evolution_chain", name="tauros")["evolutions"] == (
        "This Pokémon does not evolve."
    )


def test_move_and_ability(tools):
    move = run(tools, "get_move", name="thunderbolt")
    assert (move["type"], move["power"], move["accuracy"]) == ("Electric", 90, 100)

    ability = run(tools, "get_ability", name="levitate")
    assert "Gastly" in ability["pokemon_with_ability"]
    # Latest-gen data: Gengar lost Levitate in Gen 7.
    assert "Gengar" not in ability["pokemon_with_ability"]


def test_search_knowledge_filters_kind(tools):
    # Without "ghost", "hides under a cloth" ranks Sewaddle (sews clothes) first: Mimikyu's
    # entries say "rag", not "cloth". Worth an eval case.
    results = run(tools, "search_knowledge", query="ghost that hides under a cloth", kind="species")
    assert results["results"][0]["title"] == "Mimikyu"
    assert all(r["kind"] == "species" for r in results["results"])


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("filter_pokemon", '{"types": ["fire", "water", "grass"]}'),
        ("filter_pokemon", '{"conditions": [{"stat": "luck", "op": ">", "value": 1}]}'),
        ("get_move", "{"),
        ("get_move", "{}"),
        ("not_a_tool", "{}"),
    ],
)
def test_bad_calls_return_errors_not_exceptions(tools, name, arguments):
    assert "error" in tools.run(name, arguments)
