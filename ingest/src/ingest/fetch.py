"""Download a pinned snapshot of PokeAPI's CSV tables.

The PokeAPI repo ships the same data the REST API serves as flat CSV tables, so one
download per table replaces thousands of API calls (PokeAPI's fair-use policy asks
clients not to crawl the API).
"""

import json
from datetime import UTC, datetime

import httpx

from ingest.paths import CSV_DIR

REPO = "PokeAPI/pokeapi"
CSV_PATH = "data/v2/csv"

TABLES = [
    # Pokémon, species and forms
    "pokemon",
    "pokemon_species",
    "pokemon_species_names",
    "pokemon_species_flavor_text",
    "pokemon_forms",
    "pokemon_form_names",
    "pokemon_stats",
    "stats",
    # Types
    "pokemon_types",
    "types",
    "type_names",
    "type_efficacy",
    # Abilities
    "pokemon_abilities",
    "abilities",
    "ability_names",
    "ability_prose",
    "ability_flavor_text",
    # Moves
    "moves",
    "move_names",
    "move_effect_prose",
    "move_flavor_text",
    "move_damage_classes",
    # Evolution (items are needed for stone/held-item evolutions)
    "evolution_chains",
    "pokemon_evolution",
    "evolution_triggers",
    "items",
    "item_names",
    # Lookups
    "location_names",
    "regions",
    "generations",
    "versions",
    "version_groups",
    "languages",
]


def resolve_ref(client: httpx.Client, ref: str) -> str:
    res = client.get(
        f"https://api.github.com/repos/{REPO}/commits/{ref}",
        headers={"Accept": "application/vnd.github.sha"},
    )
    res.raise_for_status()
    return res.text.strip()


def fetch(ref: str = "master", force: bool = False) -> None:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    source_file = CSV_DIR / "source.json"

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        sha = resolve_ref(client, ref)

        if not force and source_file.is_file():
            source = json.loads(source_file.read_text())
            have_all = all((CSV_DIR / f"{t}.csv").is_file() for t in TABLES)
            if source.get("sha") == sha and have_all:
                print(f"CSVs already at {REPO}@{sha[:7]}, skipping (use --force to refetch)")
                return

        for table in TABLES:
            url = f"https://raw.githubusercontent.com/{REPO}/{sha}/{CSV_PATH}/{table}.csv"
            res = client.get(url)
            res.raise_for_status()
            (CSV_DIR / f"{table}.csv").write_bytes(res.content)
            print(f"  {table}.csv ({len(res.content) / 1024:.1f} KB)")

    source_file.write_text(
        json.dumps(
            {
                "repo": REPO,
                "sha": sha,
                "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "tables": TABLES,
            },
            indent=2,
        )
    )
    print(f"Fetched {len(TABLES)} tables from {REPO}@{sha[:7]}")
