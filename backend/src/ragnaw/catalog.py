"""Read-only queries over ragnaw.sqlite, and name resolution for everything a user can name.

Every lookup goes through `resolve`: exact match on a normalized name first, then a typo
allowance that scales with length. A tie between different entities is reported as
ambiguous ("mega charizard" -> X or Y) instead of guessing.
"""

import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

from ragnaw.text import normalize

STATS = ("hp", "attack", "defense", "sp_attack", "sp_defense", "speed")
SORTABLE = (*STATS, "base_stat_total")

MAX_EVOLUTION_METHODS = 4  # per edge; Leafeon alone has 7 location-based methods
MAX_ABILITY_HOLDERS = 20


class ResolutionError(Exception):
    """A name that didn't resolve. The message is written for the LLM to act on."""


@dataclass(frozen=True)
class Resolved:
    id: int
    name: str


class NameIndex:
    def __init__(self, entries: list[tuple[str, int, str]]):
        """entries: (alias, id, display name). Several aliases may point at one id."""
        self.by_alias: dict[str, tuple[int, str]] = {}
        for alias, id_, name in entries:
            self.by_alias.setdefault(normalize(alias), (id_, name))
        self.aliases = list(self.by_alias)

    def resolve(self, query: str, kind: str) -> Resolved:
        key = normalize(query)
        if key in self.by_alias:
            return Resolved(*self.by_alias[key])

        max_edits = max(1, len(key) // 4)
        matches = process.extract(
            key, self.aliases, scorer=Levenshtein.distance, score_cutoff=max_edits, limit=5
        )
        if matches:
            best = matches[0][1]
            ids = {self.by_alias[alias] for alias, score, _ in matches if score == best}
            if len(ids) == 1:
                return Resolved(*ids.pop())
            options = sorted(name for _, name in ids)
            raise ResolutionError(f"'{query}' is ambiguous; did you mean {' or '.join(options)}?")

        suggestions = process.extract(key, self.aliases, scorer=fuzz.WRatio, limit=3)
        names = sorted({self.by_alias[alias][1] for alias, _, _ in suggestions})
        raise ResolutionError(f"No {kind} named '{query}'. Closest: {', '.join(names)}.")


def type_label(type1: str, type2: str | None) -> str:
    return f"{type1}/{type2}" if type2 else type1


class Catalog:
    def __init__(self, db_path: Path):
        self.uri = f"{db_path.resolve().as_uri()}?mode=ro"
        with self._connect() as con:
            self.type_ids = {name: id_ for id_, name in con.execute("SELECT id, name FROM types")}
            self.efficacy = {(a, d): f for a, d, f in con.execute("SELECT * FROM type_efficacy")}

            pokemon_entries = []
            for id_, identifier, name, species_name, is_default in con.execute(
                "SELECT p.id, p.identifier, p.name, s.name, p.is_default "
                "FROM pokemon p JOIN species s ON s.id = p.species_id"
            ):
                pokemon_entries += [(name, id_, name), (identifier, id_, name)]
                if is_default:
                    pokemon_entries.append((species_name, id_, name))
            self.pokemon = NameIndex(pokemon_entries)
            self.species = NameIndex(
                [
                    entry
                    for id_, identifier, name in con.execute(
                        "SELECT id, identifier, name FROM species"
                    )
                    for entry in ((name, id_, name), (identifier, id_, name))
                ]
            )
            self.moves = NameIndex(self._names(con, "moves"))
            self.abilities = NameIndex(self._names(con, "abilities"))
            self.types = NameIndex([(name, id_, name) for name, id_ in self.type_ids.items()])

    @staticmethod
    def _names(con: sqlite3.Connection, table: str) -> list[tuple[str, int, str]]:
        return [
            entry
            for id_, identifier, name in con.execute(f"SELECT id, identifier, name FROM {table}")
            for entry in ((name, id_, name), (identifier, id_, name))
        ]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # A connection per call: cheap for a local read-only file, and safe across threads.
        con = sqlite3.connect(self.uri, uri=True)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    # --- pokemon -------------------------------------------------------------------

    def get_pokemon(self, name: str) -> dict:
        pokemon_id = self.pokemon.resolve(name, "Pokémon").id
        with self._connect() as con:
            p = con.execute(
                "SELECT p.*, s.name AS species, s.genus, s.is_legendary, s.is_mythical "
                "FROM pokemon p JOIN species s ON s.id = p.species_id WHERE p.id = ?",
                (pokemon_id,),
            ).fetchone()
            abilities = [
                {"name": a["name"], "hidden": bool(a["is_hidden"]), "effect": a["short_effect"]}
                for a in con.execute(
                    "SELECT a.name, a.short_effect, pa.is_hidden FROM pokemon_abilities pa "
                    "JOIN abilities a ON a.id = pa.ability_id WHERE pa.pokemon_id = ? "
                    "ORDER BY pa.slot",
                    (pokemon_id,),
                )
            ]
            other_forms = [
                r["name"]
                for r in con.execute(
                    "SELECT name FROM pokemon WHERE species_id = ? AND id != ? ORDER BY id",
                    (p["species_id"], pokemon_id),
                )
            ]
            entry = con.execute(
                "SELECT text FROM species_flavor_text WHERE species_id = ? ORDER BY rowid LIMIT 1",
                (p["species_id"],),
            ).fetchone()

        return {
            "name": p["name"],
            "species": p["species"],
            "genus": p["genus"],
            "types": type_label(p["type1"], p["type2"]),
            "stats": {s: p[s] for s in STATS},
            "base_stat_total": p["base_stat_total"],
            "abilities": abilities,
            "generation": p["generation"],
            "height_m": p["height_m"],
            "weight_kg": p["weight_kg"],
            "legendary": bool(p["is_legendary"]),
            "mythical": bool(p["is_mythical"]),
            "other_forms": other_forms,
            "pokedex_entry": entry["text"] if entry else None,
            "sprite_url": p["sprite_url"],
        }

    def filter_pokemon(
        self,
        types: list[str],
        ability: str | None,
        conditions: list[tuple[str, str, int]],
        generation: int | None,
        legendary: bool | None,
        include_forms: bool,
        sort_by: str,
        descending: bool,
        limit: int,
    ) -> dict:
        where, params, joins = [], [], ""
        for t in types:
            type_name = self.types.resolve(t, "type").name
            where.append("? IN (p.type1, p.type2)")
            params.append(type_name)
        if ability:
            ability_id = self.abilities.resolve(ability, "ability").id
            joins = "JOIN pokemon_abilities pa ON pa.pokemon_id = p.id AND pa.ability_id = ?"
            params.insert(0, ability_id)  # the JOIN placeholder comes before WHERE's
        for stat, op, value in conditions:
            # stat and op are validated against fixed Literals before reaching here.
            where.append(f"p.{stat} {op} ?")
            params.append(value)
        if generation is not None:
            where.append("p.generation = ?")
            params.append(generation)
        if legendary is not None:
            where.append("(s.is_legendary OR s.is_mythical) = ?")
            params.append(int(legendary))
        if not include_forms:
            where.append("p.is_default = 1")

        sql = (
            f"FROM pokemon p JOIN species s ON s.id = p.species_id {joins} "
            f"WHERE {' AND '.join(where) or '1'}"
        )
        direction = "DESC" if descending else "ASC"
        with self._connect() as con:
            total = con.execute(f"SELECT COUNT(*) {sql}", params).fetchone()[0]
            rows = con.execute(
                f"SELECT p.* {sql} ORDER BY p.{sort_by} {direction}, p.id LIMIT ?",
                [*params, limit],
            ).fetchall()
        return {
            "total_matches": total,
            "sorted_by": f"{sort_by} ({'highest' if descending else 'lowest'} first)",
            "results": [
                {
                    "name": r["name"],
                    "types": type_label(r["type1"], r["type2"]),
                    **{s: r[s] for s in STATS},
                    "base_stat_total": r["base_stat_total"],
                }
                for r in rows
            ],
        }

    # --- types ---------------------------------------------------------------------

    def type_matchups(self, types: list[str] | None, pokemon: str | None) -> dict:
        subject = None
        if pokemon:
            p = self.get_pokemon(pokemon)
            subject, type_names = p["name"], p["types"].split("/")
        else:
            type_names = [self.types.resolve(t, "type").name for t in types or []]
        if not 1 <= len(type_names) <= 2:
            raise ResolutionError("Give one or two types, or a Pokémon name.")

        defending = [self.type_ids[t] for t in type_names]
        buckets: dict[str, list[str]] = defaultdict(list)
        labels = {4.0: "4x", 2.0: "2x", 0.5: "0.5x", 0.25: "0.25x", 0.0: "immune"}
        order = list(labels.values())
        for attacker, attacker_id in self.type_ids.items():
            factor = 1.0
            for d in defending:
                factor *= self.efficacy[(attacker_id, d)]
            if factor != 1.0:
                buckets[labels[factor]].append(attacker)

        offense = {
            t: sorted(
                target
                for target, target_id in self.type_ids.items()
                if self.efficacy[(self.type_ids[t], target_id)] == 2.0
            )
            for t in type_names
        }
        return {
            "pokemon": subject,
            "defending_types": "/".join(type_names),
            "damage_taken": {k: sorted(buckets[k]) for k in order if k in buckets},
            "super_effective_against": offense,
            "note": "Type chart only; abilities like Levitate or Flash Fire can change these.",
        }

    # --- evolutions ----------------------------------------------------------------

    def evolution_chain(self, name: str) -> dict:
        try:
            species_id = self.species.resolve(name, "Pokémon").id
        except ResolutionError:
            # Forms resolve through the Pokémon index ("alolan raichu" -> Raichu's chain).
            pokemon_id = self.pokemon.resolve(name, "Pokémon").id
            with self._connect() as con:
                species_id = con.execute(
                    "SELECT species_id FROM pokemon WHERE id = ?", (pokemon_id,)
                ).fetchone()[0]

        with self._connect() as con:
            chain_id = con.execute(
                "SELECT evolution_chain_id FROM species WHERE id = ?", (species_id,)
            ).fetchone()[0]
            members = con.execute(
                "SELECT id, name, evolves_from_species_id FROM species "
                "WHERE evolution_chain_id = ? ORDER BY id",
                (chain_id,),
            ).fetchall()
            edges = con.execute(
                "SELECT fs.name AS from_species, ts.name AS to_species, "
                "fp.name AS from_form, tp.name AS to_form, e.method "
                "FROM evolutions e "
                "JOIN species fs ON fs.id = e.from_species_id "
                "JOIN species ts ON ts.id = e.to_species_id "
                "LEFT JOIN pokemon fp ON fp.id = e.from_pokemon_id "
                "LEFT JOIN pokemon tp ON tp.id = e.to_pokemon_id "
                "WHERE ts.evolution_chain_id = ? ORDER BY ts.id",
                (chain_id,),
            ).fetchall()

        methods: dict[tuple[str, str], list[str]] = defaultdict(list)
        for e in edges:
            key = (e["from_form"] or e["from_species"], e["to_form"] or e["to_species"])
            methods[key].append(e["method"])

        evolutions = []
        for (source, target), found in methods.items():
            shown = found[:MAX_EVOLUTION_METHODS]
            if len(found) > len(shown):
                shown.append(f"...and {len(found) - len(shown)} more game-specific methods")
            evolutions.append({"from": source, "to": target, "methods": shown})

        # List members in evolution order (Pichu, Pikachu, Raichu), not by Pokédex number.
        children: dict[int | None, list] = defaultdict(list)
        for m in members:
            children[m["evolves_from_species_id"]].append(m)
        ordered, queue = [], list(children[None])
        while queue:
            m = queue.pop(0)
            ordered.append(m["name"])
            queue.extend(children[m["id"]])
        # Anything unreachable from a base (bad data) still gets listed.
        ordered += [m["name"] for m in members if m["name"] not in ordered]
        return {
            "members": ordered,
            "evolutions": evolutions or "This Pokémon does not evolve.",
        }

    # --- moves and abilities -------------------------------------------------------

    def get_move(self, name: str) -> dict:
        move_id = self.moves.resolve(name, "move").id
        with self._connect() as con:
            m = con.execute("SELECT * FROM moves WHERE id = ?", (move_id,)).fetchone()
        return {
            "name": m["name"],
            "type": m["type"],
            "category": m["damage_class"],
            "power": m["power"],
            "accuracy": m["accuracy"],
            "pp": m["pp"],
            "priority": m["priority"],
            "effect_chance_percent": m["effect_chance"],
            "effect": m["effect"] or m["short_effect"] or m["flavor_text"],
            "generation": m["generation"],
        }

    def get_ability(self, name: str) -> dict:
        ability_id = self.abilities.resolve(name, "ability").id
        with self._connect() as con:
            a = con.execute("SELECT * FROM abilities WHERE id = ?", (ability_id,)).fetchone()
            holders = con.execute(
                "SELECT p.name, pa.is_hidden FROM pokemon_abilities pa "
                "JOIN pokemon p ON p.id = pa.pokemon_id WHERE pa.ability_id = ? ORDER BY p.id",
                (ability_id,),
            ).fetchall()
        shown = [f"{h['name']}{' (hidden)' if h['is_hidden'] else ''}" for h in holders]
        return {
            "name": a["name"],
            "effect": a["effect"] or a["short_effect"] or a["flavor_text"],
            "generation": a["generation"],
            "pokemon_with_ability": shown[:MAX_ABILITY_HOLDERS],
            "total_pokemon_with_ability": len(holders),
        }
