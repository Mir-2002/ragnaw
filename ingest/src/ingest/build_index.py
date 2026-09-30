"""Build the dense search index over prose documents.

Documents are short, per-entity chunks: Pokédex entries per species, and ability and move
effects. Chunks are packed by real token count to MAX_TOKENS: MiniLM truncates at 256, and
mean pooling over long chunks dilutes individual facts (a 150-token Pikachu chunk didn't
match "stores electricity in its cheeks").
Structured data (stats, types, matchups) is left to the SQLite tools.

The backend builds BM25 over documents.json at startup; at this corpus size that takes
milliseconds and saves shipping another artifact.

Writes to backend/data/:
- documents.json   chunk text + metadata, in the same order as the embedding rows
- embeddings.npy   float32 (n_docs, dim), L2-normalized so dot product = cosine
- manifest.json    written last; the backend treats its presence as "data ready"
"""

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache

import numpy as np
from fastembed import TextEmbedding
from tokenizers import Tokenizer

from ingest.build_db import DB_PATH
from ingest.paths import INGEST_ROOT, OUTPUT_DIR

# The backend reads this from manifest.json, so query and document vectors always match.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_CACHE_DIR = INGEST_ROOT / ".cache" / "models"
SCHEMA_VERSION = 1

MAX_TOKENS = 128
MODEL_WINDOW = 256
SPECIAL_TOKENS = 2  # [CLS] and [SEP]

TokenCounter = Callable[[str], int]

DOCUMENTS_FILE = "documents.json"
EMBEDDINGS_FILE = "embeddings.npy"
MANIFEST_FILE = "manifest.json"


def make_token_counter() -> TokenCounter:
    tokenizer = Tokenizer.from_pretrained(EMBEDDING_MODEL)
    # The Hub config pads every encoding to 128, which would make each word count as 128.
    tokenizer.no_padding()
    tokenizer.no_truncation()

    # BERT pre-tokenization splits on whitespace first, so per-word counts sum exactly.
    @cache
    def word_tokens(word: str) -> int:
        return len(tokenizer.encode(word, add_special_tokens=False).ids)

    return lambda text: sum(word_tokens(w) for w in text.split())


def pack(
    header: str, pieces: list[str], count: TokenCounter, max_tokens: int = MAX_TOKENS
) -> list[str]:
    """Greedily pack text pieces into chunks of at most max_tokens, each starting with header.

    Repeating the header in every chunk keeps each one attributable to its entity when it's
    retrieved alone. Pieces are kept whole unless one alone exceeds the budget, in which
    case it's split on word boundaries.
    """
    budget = max_tokens - SPECIAL_TOKENS - count(header)
    segments: list[tuple[list[str], int]] = []
    for piece in pieces:
        run: list[str] = []
        run_tokens = 0
        for word in piece.split():
            n = count(word)
            if run and run_tokens + n > budget:
                segments.append((run, run_tokens))
                run, run_tokens = [], 0
            run.append(word)
            run_tokens += n
        if run:
            segments.append((run, run_tokens))

    chunks: list[tuple[list[str], int]] = []
    for words, n in segments:
        if chunks and chunks[-1][1] + n <= budget:
            chunks[-1] = (chunks[-1][0] + words, chunks[-1][1] + n)
        else:
            chunks.append((words, n))
    return [f"{header} {' '.join(words)}" for words, _ in chunks]


def type_label(type1: str, type2: str | None) -> str:
    return f"{type1}/{type2}" if type2 else type1


def species_documents(con: sqlite3.Connection, count: TokenCounter) -> list[dict]:
    flavor: dict[int, list[str]] = defaultdict(list)
    for species_id, text in con.execute(
        "SELECT species_id, text FROM species_flavor_text ORDER BY rowid"
    ):
        flavor[species_id].append(text)

    forms: dict[int, list[str]] = defaultdict(list)
    for species_id, name, type1, type2 in con.execute(
        "SELECT species_id, name, type1, type2 FROM pokemon WHERE is_default = 0 ORDER BY id"
    ):
        forms[species_id].append(f"{name} ({type_label(type1, type2)})")

    docs = []
    rows = con.execute(
        "SELECT s.id, s.identifier, s.name, s.genus, p.type1, p.type2 FROM species s "
        "JOIN pokemon p ON p.species_id = s.id AND p.is_default = 1 ORDER BY s.id"
    )
    for species_id, identifier, name, genus, type1, type2 in rows:
        genus_part = f", the {genus}" if genus else ""
        header = f"{name}{genus_part} ({type_label(type1, type2)} type)."
        pieces = []
        if forms[species_id]:
            pieces.append(f"Other forms: {', '.join(forms[species_id])}.")
        pieces.extend(flavor[species_id])
        for n, text in enumerate(pack(header, pieces, count)):
            docs.append(
                {
                    "id": f"species:{species_id}:{n}",
                    "kind": "species",
                    "entity_id": species_id,
                    "title": name,
                    "text": text,
                    "url": f"https://pokeapi.co/api/v2/pokemon-species/{identifier}",
                }
            )
    return docs


def move_documents(con: sqlite3.Connection, count: TokenCounter) -> list[dict]:
    docs = []
    rows = con.execute(
        "SELECT id, identifier, name, type, damage_class, effect_chance, short_effect, effect, "
        "flavor_text FROM moves ORDER BY id"
    )
    for move_id, identifier, name, type_, damage_class, chance, short, effect, flavor in rows:
        header = f"{name} ({type_} {damage_class} move)."
        pieces = [effect or short or ""]
        if chance:
            pieces.append(f"Effect chance: {chance}%.")
        if flavor:
            pieces.append(flavor)
        for n, text in enumerate(pack(header, [p for p in pieces if p], count)):
            docs.append(
                {
                    "id": f"move:{move_id}:{n}",
                    "kind": "move",
                    "entity_id": move_id,
                    "title": name,
                    "text": text,
                    "url": f"https://pokeapi.co/api/v2/move/{identifier}",
                }
            )
    return docs


def ability_documents(con: sqlite3.Connection, count: TokenCounter) -> list[dict]:
    docs = []
    rows = con.execute(
        "SELECT id, identifier, name, short_effect, effect, flavor_text FROM abilities ORDER BY id"
    )
    for ability_id, identifier, name, short, effect, flavor in rows:
        header = f"{name} (ability)."
        pieces = [p for p in (effect or short, flavor) if p]
        for n, text in enumerate(pack(header, pieces, count)):
            docs.append(
                {
                    "id": f"ability:{ability_id}:{n}",
                    "kind": "ability",
                    "entity_id": ability_id,
                    "title": name,
                    "text": text,
                    "url": f"https://pokeapi.co/api/v2/ability/{identifier}",
                }
            )
    return docs


def build_index() -> None:
    if not DB_PATH.is_file():
        raise SystemExit(f"{DB_PATH} not found; run `ingest build-db` first")

    count = make_token_counter()
    con = sqlite3.connect(DB_PATH)
    docs = (
        species_documents(con, count) + move_documents(con, count) + ability_documents(con, count)
    )
    pokeapi_sha = con.execute("SELECT value FROM metadata WHERE key = 'pokeapi_sha'").fetchone()[0]
    con.close()

    longest = max(count(d["text"]) + SPECIAL_TOKENS for d in docs)
    if longest > MODEL_WINDOW:
        raise SystemExit(f"a chunk has {longest} tokens; MiniLM truncates at {MODEL_WINDOW}")

    print(f"Embedding {len(docs)} chunks with {EMBEDDING_MODEL}…")
    model = TextEmbedding(EMBEDDING_MODEL, cache_dir=str(MODEL_CACHE_DIR))
    vectors = np.array(list(model.embed([d["text"] for d in docs], batch_size=64)), np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

    # Manifest goes last and old manifests go first, so a failed build never looks ready.
    (OUTPUT_DIR / MANIFEST_FILE).unlink(missing_ok=True)
    (OUTPUT_DIR / DOCUMENTS_FILE).write_text(json.dumps(docs, ensure_ascii=False), "utf-8")
    np.save(OUTPUT_DIR / EMBEDDINGS_FILE, vectors)

    counts: dict[str, int] = defaultdict(int)
    for d in docs:
        counts[d["kind"]] += 1
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": int(vectors.shape[1]),
        "max_chunk_tokens": MAX_TOKENS,
        "documents": len(docs),
        "documents_by_kind": dict(counts),
        "files": {
            "db": DB_PATH.name,
            "documents": DOCUMENTS_FILE,
            "embeddings": EMBEDDINGS_FILE,
        },
        "pokeapi_sha": pokeapi_sha,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (OUTPUT_DIR / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2), "utf-8")

    size_kb = (OUTPUT_DIR / EMBEDDINGS_FILE).stat().st_size / 1024
    print(f"Wrote {len(docs)} chunks {dict(counts)}; {EMBEDDINGS_FILE} {size_kb:.0f} KB")
