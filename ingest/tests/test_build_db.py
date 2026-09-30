"""Known-fact checks against the built DB. Run `uv run ingest build-db` first."""

import sqlite3

import pytest

from ingest.build_db import DB_PATH

pytestmark = pytest.mark.skipif(not DB_PATH.is_file(), reason="run `ingest build-db` first")


@pytest.fixture(scope="module")
def db():
    con = sqlite3.connect(DB_PATH)
    yield con
    con.close()


def pokemon(db, identifier):
    return db.execute(
        "SELECT name, type1, type2, base_stat_total FROM pokemon WHERE identifier = ?",
        (identifier,),
    ).fetchone()


def test_uses_latest_generation_types(db):
    # Clefairy was Normal before Gen 6.
    assert pokemon(db, "clefairy")[1:3] == ("Fairy", None)


def test_keeps_forms_that_change_battle_data(db):
    assert pokemon(db, "charizard-mega-x") == ("Mega Charizard X", "Fire", "Dragon", 634)
    assert pokemon(db, "raichu-alola")[:3] == ("Alolan Raichu", "Electric", "Psychic")
    assert pokemon(db, "rotom-wash")[1:3] == ("Electric", "Water")


def test_drops_cosmetic_forms(db):
    dropped = db.execute(
        "SELECT COUNT(*) FROM pokemon WHERE identifier LIKE '%-gmax' "
        "OR identifier LIKE '%totem%' OR identifier LIKE 'pikachu-%-cap'"
    ).fetchone()[0]
    assert dropped == 0


def test_default_forms_use_species_name(db):
    assert pokemon(db, "kyogre")[0] == "Kyogre"
    assert pokemon(db, "castform")[0] == "Castform"


def test_type_chart(db):
    def factor(attacker, defender):
        return db.execute(
            "SELECT e.factor FROM type_efficacy e "
            "JOIN types a ON a.id = e.attacking_type_id "
            "JOIN types d ON d.id = e.defending_type_id WHERE a.name = ? AND d.name = ?",
            (attacker, defender),
        ).fetchone()[0]

    assert db.execute("SELECT COUNT(*) FROM types").fetchone()[0] == 18
    assert factor("Fire", "Grass") == 2.0
    assert factor("Ground", "Flying") == 0.0
    assert factor("Dragon", "Fairy") == 0.0


def test_evolution_methods(db):
    def methods(from_identifier):
        return db.execute(
            "SELECT s2.name, p.name, e.method FROM evolutions e "
            "JOIN species s1 ON s1.id = e.from_species_id "
            "JOIN species s2 ON s2.id = e.to_species_id "
            "LEFT JOIN pokemon p ON p.id = e.to_pokemon_id WHERE s1.identifier = ?",
            (from_identifier,),
        ).fetchall()

    assert ("Raichu", "Alolan Raichu", "use Thunder Stone in Alola") in methods("pikachu")
    assert ("Hitmontop", None, "level 20 with Attack = Defense") in methods("tyrogue")
    assert ("Umbreon", None, "level up with high friendship during night") in methods("eevee")


def test_every_species_has_flavor_text(db):
    missing = db.execute(
        "SELECT COUNT(*) FROM species WHERE id NOT IN (SELECT species_id FROM species_flavor_text)"
    ).fetchone()[0]
    assert missing == 0
