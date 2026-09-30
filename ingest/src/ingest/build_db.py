"""Build backend/data/ragnaw.sqlite from the fetched CSVs.

This DB backs the structured tools (get_pokemon, filter_pokemon, get_type_matchups,
get_evolution_chain, get_move, get_ability). Scope decisions:

- Latest-generation data only. PokeAPI's main CSVs already hold current values; past
  types, stats and move values live in separate *_past / changelog tables we don't fetch.
- A non-default variant is kept only if its types, stats or abilities differ from every
  variant already kept for that species. This keeps Megas, regional forms and battle forms
  (Rotom-Wash, Deoxys-Attack) while dropping Gigantamax, Totem and cosmetic-only forms.
- English names and text only. Shadow moves (Colosseum/XD) are dropped.
"""

import csv
import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime

from ingest.paths import CSV_DIR, OUTPUT_DIR

DB_PATH = OUTPUT_DIR / "ragnaw.sqlite"
SCHEMA_VERSION = 1

ENGLISH = "9"
FIRST_NON_CANON_ID = 10000  # moves/types past this are shadow/unknown, not main-series

STAT_COLUMNS = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}

SPRITE_URL = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/"
    "official-artwork/{id}.png"
)

SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE types (id INTEGER PRIMARY KEY, identifier TEXT NOT NULL, name TEXT NOT NULL);

CREATE TABLE type_efficacy (
    attacking_type_id INTEGER NOT NULL REFERENCES types(id),
    defending_type_id INTEGER NOT NULL REFERENCES types(id),
    factor REAL NOT NULL,
    PRIMARY KEY (attacking_type_id, defending_type_id)
);

CREATE TABLE species (
    id INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL,
    name TEXT NOT NULL,
    genus TEXT,
    generation INTEGER NOT NULL,
    evolves_from_species_id INTEGER REFERENCES species(id),
    evolution_chain_id INTEGER,
    is_baby INTEGER NOT NULL,
    is_legendary INTEGER NOT NULL,
    is_mythical INTEGER NOT NULL,
    capture_rate INTEGER
);

CREATE TABLE species_flavor_text (
    species_id INTEGER NOT NULL REFERENCES species(id),
    version TEXT NOT NULL,
    text TEXT NOT NULL
);

CREATE TABLE pokemon (
    id INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    species_id INTEGER NOT NULL REFERENCES species(id),
    is_default INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    type1 TEXT NOT NULL,
    type2 TEXT,
    hp INTEGER NOT NULL,
    attack INTEGER NOT NULL,
    defense INTEGER NOT NULL,
    sp_attack INTEGER NOT NULL,
    sp_defense INTEGER NOT NULL,
    speed INTEGER NOT NULL,
    base_stat_total INTEGER NOT NULL,
    height_m REAL,
    weight_kg REAL,
    sprite_url TEXT NOT NULL
);

CREATE TABLE abilities (
    id INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    generation INTEGER NOT NULL,
    short_effect TEXT,
    effect TEXT,
    flavor_text TEXT
);

CREATE TABLE pokemon_abilities (
    pokemon_id INTEGER NOT NULL REFERENCES pokemon(id),
    ability_id INTEGER NOT NULL REFERENCES abilities(id),
    is_hidden INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    PRIMARY KEY (pokemon_id, slot)
);

CREATE TABLE moves (
    id INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    damage_class TEXT NOT NULL,
    power INTEGER,
    pp INTEGER,
    accuracy INTEGER,
    priority INTEGER NOT NULL,
    effect_chance INTEGER,
    generation INTEGER NOT NULL,
    short_effect TEXT,
    effect TEXT,
    flavor_text TEXT
);

CREATE TABLE evolutions (
    from_species_id INTEGER NOT NULL REFERENCES species(id),
    to_species_id INTEGER NOT NULL REFERENCES species(id),
    -- Set only when the evolution starts from / produces a non-default form (Alolan Raichu).
    from_pokemon_id INTEGER REFERENCES pokemon(id),
    to_pokemon_id INTEGER REFERENCES pokemon(id),
    method TEXT NOT NULL
);

CREATE INDEX idx_pokemon_species ON pokemon(species_id);
CREATE INDEX idx_species_chain ON species(evolution_chain_id);
CREATE INDEX idx_evolutions_to ON evolutions(to_species_id);
"""


def read(table: str) -> list[dict[str, str]]:
    with open(CSV_DIR / f"{table}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def num(value: str) -> int | None:
    return int(value) if value != "" else None


def clean(text: str) -> str:
    """Collapse game-text line breaks, form feeds and soft hyphens into plain prose."""
    return " ".join(text.replace("\xad", "").replace("‐ ", "").split())


def english(rows: list[dict[str, str]], id_col: str, lang_col: str = "local_language_id"):
    return {r[id_col]: r for r in rows if r[lang_col] == ENGLISH}


def latest_english_text(
    rows: list[dict[str, str]], id_col: str, key_col: str, order: dict[str, int]
) -> dict[str, str]:
    """Most recent English flavor text per entity, by game release order."""
    best: dict[str, tuple[int, str]] = {}
    for r in rows:
        if r["language_id"] != ENGLISH:
            continue
        rank = order.get(r[key_col], -1)
        if r[id_col] not in best or rank > best[r[id_col]][0]:
            best[r[id_col]] = (rank, clean(r["flavor_text"]))
    return {k: text for k, (_, text) in best.items()}


def titleize(identifier: str) -> str:
    return identifier.replace("-", " ").title()


class Lookups:
    """English display names for everything an evolution method can reference."""

    def __init__(self, species_names: dict[str, str], pokemon_names: dict[str, str]):
        self.species = species_names
        self.pokemon = pokemon_names
        self.items = {k: r["name"] for k, r in english(read("item_names"), "item_id").items()}
        self.moves = {k: r["name"] for k, r in english(read("move_names"), "move_id").items()}
        self.types = {k: r["name"] for k, r in english(read("type_names"), "type_id").items()}
        self.locations = {
            k: r["name"] for k, r in english(read("location_names"), "location_id").items()
        }
        self.regions = {r["id"]: titleize(r["identifier"]) for r in read("regions")}
        self.triggers = {r["id"]: r["identifier"] for r in read("evolution_triggers")}


def describe_evolution(r: dict[str, str], names: Lookups) -> str:
    trigger = names.triggers[r["evolution_trigger_id"]]
    if trigger == "level-up":
        parts = [f"level {r['minimum_level']}" if r["minimum_level"] else "level up"]
    elif trigger == "use-item":
        parts = [f"use {names.items.get(r['trigger_item_id'], 'an item')}"]
    elif trigger == "trade":
        parts = ["trade"]
        if r["trade_species_id"]:
            parts.append(f"for {names.species[r['trade_species_id']]}")
    else:
        parts = [trigger.replace("-", " ")]
        if r["minimum_level"]:
            parts.append(f"at level {r['minimum_level']}")

    if r["held_item_id"]:
        parts.append(f"while holding {names.items.get(r['held_item_id'], 'an item')}")
    if r["known_move_id"]:
        parts.append(f"knowing {names.moves[r['known_move_id']]}")
    if r["known_move_type_id"]:
        parts.append(f"knowing a {names.types[r['known_move_type_id']]}-type move")
    if r["used_move_id"]:
        times = f" {r['minimum_move_count']} times" if r["minimum_move_count"] else ""
        parts.append(f"after using {names.moves[r['used_move_id']]}{times}")
    if r["minimum_happiness"]:
        parts.append("with high friendship")
    if r["minimum_affection"]:
        parts.append("with high affection")
    if r["minimum_beauty"]:
        parts.append("with high beauty")
    if r["relative_physical_stats"]:
        relation = {"1": ">", "0": "=", "-1": "<"}[r["relative_physical_stats"]]
        parts.append(f"with Attack {relation} Defense")
    if r["time_of_day"]:
        parts.append(f"during {r['time_of_day'].replace('-', ' ')}")
    if r["gender_id"]:
        parts.append({"1": "(female only)", "2": "(male only)"}[r["gender_id"]])
    if r["location_id"]:
        parts.append(f"at {names.locations.get(r['location_id'], 'a specific location')}")
    if r["region_id"]:
        parts.append(f"in {names.regions[r['region_id']]}")
    if r["near_special_rock"] == "1":
        parts.append("near a special rock")
    if r["party_species_id"]:
        parts.append(f"with {names.species[r['party_species_id']]} in the party")
    if r["party_type_id"]:
        parts.append(f"with a {names.types[r['party_type_id']]}-type Pokémon in the party")
    if r["needs_overworld_rain"] == "1":
        parts.append("while it's raining")
    if r["turn_upside_down"] == "1":
        parts.append("with the console held upside down")
    if r["needs_multiplayer"] == "1":
        parts.append("in Union Circle")
    if r["minimum_steps"]:
        parts.append(f"after walking {r['minimum_steps']} steps")
    if r["minimum_damage_taken"]:
        parts.append(f"after taking at least {r['minimum_damage_taken']} damage")
    if r["percentage_chance"]:
        parts.append(f"({r['percentage_chance']}% chance)")
    return " ".join(parts)


def build_db() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source = json.loads((CSV_DIR / "source.json").read_text())

    version_group_order = {r["id"]: int(r["order"]) for r in read("version_groups")}
    version_group_generation = {r["id"]: int(r["generation_id"]) for r in read("version_groups")}
    versions = read("versions")
    version_order = {r["id"]: version_group_order[r["version_group_id"]] for r in versions}
    version_names = {r["id"]: r["identifier"] for r in versions}

    # --- types -----------------------------------------------------------------
    type_names = {k: r["name"] for k, r in english(read("type_names"), "type_id").items()}
    efficacy = read("type_efficacy")
    canon_type_ids = {r["damage_type_id"] for r in efficacy}  # the 18 battle types
    types = {r["id"]: type_names[r["id"]] for r in read("types") if r["id"] in canon_type_ids}

    # --- species ---------------------------------------------------------------
    species_names = english(read("pokemon_species_names"), "pokemon_species_id")
    species_rows = read("pokemon_species")
    species_name = {r["id"]: species_names[r["id"]]["name"] for r in species_rows}

    flavor_by_species: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for r in read("pokemon_species_flavor_text"):
        if r["language_id"] == ENGLISH:
            flavor_by_species[r["species_id"]].append(
                (version_order[r["version_id"]], version_names[r["version_id"]], r["flavor_text"])
            )

    # --- pokemon variants --------------------------------------------------------
    types_by_pokemon: dict[str, list[str]] = defaultdict(list)
    for r in sorted(read("pokemon_types"), key=lambda r: int(r["slot"])):
        types_by_pokemon[r["pokemon_id"]].append(types[r["type_id"]])

    stat_ids = {r["id"]: r["identifier"] for r in read("stats")}
    stats_by_pokemon: dict[str, dict[str, int]] = defaultdict(dict)
    for r in read("pokemon_stats"):
        identifier = stat_ids[r["stat_id"]]
        if identifier in STAT_COLUMNS:
            stats_by_pokemon[r["pokemon_id"]][STAT_COLUMNS[identifier]] = int(r["base_stat"])

    ability_rows = [r for r in read("abilities") if r["is_main_series"] == "1"]
    main_ability_ids = {r["id"] for r in ability_rows}
    abilities_by_pokemon: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in read("pokemon_abilities"):
        if r["ability_id"] in main_ability_ids:
            abilities_by_pokemon[r["pokemon_id"]].append(r)

    def signature(pokemon_id: str) -> tuple:
        return (
            tuple(types_by_pokemon[pokemon_id]),
            tuple(sorted(stats_by_pokemon[pokemon_id].items())),
            frozenset((a["ability_id"], a["is_hidden"]) for a in abilities_by_pokemon[pokemon_id]),
        )

    forms = read("pokemon_forms")
    default_form = {f["pokemon_id"]: f for f in forms if f["is_default"] == "1"}
    pokemon_id_by_form = {f["id"]: f["pokemon_id"] for f in forms}
    form_names = english(read("pokemon_form_names"), "pokemon_form_id")

    def display_name(p: dict[str, str]) -> str:
        base = species_name[p["species_id"]]
        if p["is_default"] == "1":
            return base
        form = default_form.get(p["id"])
        names = form_names.get(form["id"]) if form else None
        if names and names["pokemon_name"]:
            return names["pokemon_name"]
        return f"{base} ({names['form_name']})" if names and names["form_name"] else base

    species_generation = {r["id"]: int(r["generation_id"]) for r in species_rows}
    all_pokemon = read("pokemon")
    # Defaults first, so variants are compared against the default form.
    all_pokemon.sort(key=lambda p: (p["is_default"] != "1", int(p["id"])))
    seen: dict[str, set[tuple]] = defaultdict(set)
    kept: list[dict] = []
    for p in all_pokemon:
        sig = signature(p["id"])
        if p["is_default"] != "1" and sig in seen[p["species_id"]]:
            continue
        seen[p["species_id"]].add(sig)

        stats = stats_by_pokemon[p["id"]]
        form = default_form.get(p["id"])
        if p["is_default"] == "1" or not form:
            generation = species_generation[p["species_id"]]
        else:
            generation = version_group_generation[form["introduced_in_version_group_id"]]
        poke_types = types_by_pokemon[p["id"]]
        kept.append(
            {
                "id": int(p["id"]),
                "identifier": p["identifier"],
                "name": display_name(p),
                "species_id": int(p["species_id"]),
                "is_default": int(p["is_default"]),
                "generation": generation,
                "type1": poke_types[0],
                "type2": poke_types[1] if len(poke_types) > 1 else None,
                **stats,
                "base_stat_total": sum(stats.values()),
                "height_m": int(p["height"]) / 10 if p["height"] else None,
                "weight_kg": int(p["weight"]) / 10 if p["weight"] else None,
                "sprite_url": SPRITE_URL.format(id=p["id"]),
            }
        )
    kept_ids = {str(p["id"]) for p in kept}
    variant_ids = {str(p["id"]) for p in kept if not p["is_default"]}

    # --- abilities ---------------------------------------------------------------
    ability_names = english(read("ability_names"), "ability_id")
    ability_prose = english(read("ability_prose"), "ability_id")
    ability_flavor = latest_english_text(
        read("ability_flavor_text"), "ability_id", "version_group_id", version_group_order
    )

    # --- moves -------------------------------------------------------------------
    move_names = english(read("move_names"), "move_id")
    move_prose = english(read("move_effect_prose"), "move_effect_id")
    move_flavor = latest_english_text(
        read("move_flavor_text"), "move_id", "version_group_id", version_group_order
    )
    damage_classes = {r["id"]: r["identifier"] for r in read("move_damage_classes")}

    # --- evolutions --------------------------------------------------------------
    pokemon_names = {str(p["id"]): p["name"] for p in kept}
    lookups = Lookups(species_name, pokemon_names)
    evolves_from = {r["id"]: r["evolves_from_species_id"] for r in species_rows}
    evolutions: list[tuple] = []
    for r in read("pokemon_evolution"):
        from_species = evolves_from[r["evolved_species_id"]]
        if not from_species:
            continue
        from_pokemon = pokemon_id_by_form.get(r["required_pokemon_form_id"])
        to_pokemon = pokemon_id_by_form.get(r["evolved_pokemon_form_id"])
        row = (
            int(from_species),
            int(r["evolved_species_id"]),
            int(from_pokemon) if from_pokemon in variant_ids else None,
            int(to_pokemon) if to_pokemon in variant_ids else None,
            describe_evolution(r, lookups),
        )
        if row not in evolutions:
            evolutions.append(row)

    # --- write -------------------------------------------------------------------
    tmp_path = DB_PATH.with_suffix(".sqlite.tmp")
    tmp_path.unlink(missing_ok=True)
    con = sqlite3.connect(tmp_path)
    con.executescript(SCHEMA)

    con.executemany(
        "INSERT INTO types VALUES (?, ?, ?)",
        [
            (int(i), r["identifier"], types[i])
            for i, r in ((r["id"], r) for r in read("types"))
            if i in types
        ],
    )
    con.executemany(
        "INSERT INTO type_efficacy VALUES (?, ?, ?)",
        [
            (int(r["damage_type_id"]), int(r["target_type_id"]), int(r["damage_factor"]) / 100)
            for r in efficacy
        ],
    )
    con.executemany(
        "INSERT INTO species VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                int(r["id"]),
                r["identifier"],
                species_name[r["id"]],
                species_names[r["id"]]["genus"] or None,
                int(r["generation_id"]),
                num(r["evolves_from_species_id"]),
                num(r["evolution_chain_id"]),
                int(r["is_baby"]),
                int(r["is_legendary"]),
                int(r["is_mythical"]),
                num(r["capture_rate"]),
            )
            for r in species_rows
        ],
    )

    flavor_rows = []
    for species_id, entries in flavor_by_species.items():
        seen_texts: set[str] = set()
        for _, version, raw in sorted(entries, reverse=True):  # newest first
            text = clean(raw)
            if text not in seen_texts:
                seen_texts.add(text)
                flavor_rows.append((int(species_id), version, text))
    con.executemany("INSERT INTO species_flavor_text VALUES (?, ?, ?)", flavor_rows)

    columns = list(kept[0])
    con.executemany(
        f"INSERT INTO pokemon ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        [tuple(p[c] for c in columns) for p in kept],
    )

    con.executemany(
        "INSERT INTO abilities VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                int(r["id"]),
                r["identifier"],
                ability_names[r["id"]]["name"],
                int(r["generation_id"]),
                clean(ability_prose[r["id"]]["short_effect"]) if r["id"] in ability_prose else None,
                clean(ability_prose[r["id"]]["effect"]) if r["id"] in ability_prose else None,
                ability_flavor.get(r["id"]),
            )
            for r in ability_rows
        ],
    )
    con.executemany(
        "INSERT INTO pokemon_abilities VALUES (?, ?, ?, ?)",
        [
            (int(pid), int(a["ability_id"]), int(a["is_hidden"]), int(a["slot"]))
            for pid in kept_ids
            for a in abilities_by_pokemon[pid]
        ],
    )

    move_rows = []
    for r in read("moves"):
        if int(r["id"]) >= FIRST_NON_CANON_ID:
            continue
        prose = move_prose.get(r["effect_id"])
        move_rows.append(
            (
                int(r["id"]),
                r["identifier"],
                move_names[r["id"]]["name"],
                types[r["type_id"]],
                damage_classes[r["damage_class_id"]],
                num(r["power"]),
                num(r["pp"]),
                num(r["accuracy"]),
                int(r["priority"]),
                num(r["effect_chance"]),
                int(r["generation_id"]),
                clean(prose["short_effect"]) if prose else None,
                clean(prose["effect"]) if prose else None,
                move_flavor.get(r["id"]),
            )
        )
    con.executemany(
        "INSERT INTO moves VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", move_rows
    )
    con.executemany("INSERT INTO evolutions VALUES (?, ?, ?, ?, ?)", evolutions)

    counts = {
        table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("species", "pokemon", "abilities", "moves", "evolutions")
    }
    con.executemany(
        "INSERT INTO metadata VALUES (?, ?)",
        [
            ("schema_version", str(SCHEMA_VERSION)),
            ("pokeapi_repo", source["repo"]),
            ("pokeapi_sha", source["sha"]),
            ("built_at", datetime.now(UTC).isoformat(timespec="seconds")),
        ],
    )
    con.commit()
    con.execute("VACUUM")
    con.close()
    tmp_path.replace(DB_PATH)

    size_kb = DB_PATH.stat().st_size / 1024
    summary = ", ".join(f"{n} {t}" for t, n in counts.items())
    print(f"Wrote {DB_PATH.name} ({size_kb:.0f} KB): {summary}")
