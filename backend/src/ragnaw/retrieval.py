"""Hybrid search over the prose index built by `ingest build-index`.

Dense (MiniLM) and BM25 rankings are merged with reciprocal rank fusion, then documents
whose entity is named in the query get a boost. Dense search alone ranks Sirfetch'd above
Farfetch'd for the query "Farfetch'd"; exact names are what BM25 and the boost are for.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import bm25s
import numpy as np
import Stemmer
from fastembed import TextEmbedding
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

from ragnaw.text import normalize

RRF_K = 60  # standard reciprocal rank fusion constant
CANDIDATES = 50  # per-ranker depth fed into fusion
NAME_BOOST = 1 / RRF_K  # as much as a first place in one ranker
MAX_NAME_WORDS = 3  # longest entity name we try to spot, e.g. "mr mime jr"
MIN_FUZZY_LENGTH = 5  # shorter typos are too ambiguous to correct
MAX_CHUNKS_PER_ENTITY = 2  # keep one entity's chunks from crowding out the rest


@dataclass(frozen=True)
class Hit:
    doc: dict
    score: float


class KnowledgeIndex:
    def __init__(self, data_dir: Path, model_cache_dir: Path | None = None):
        manifest = json.loads((data_dir / "manifest.json").read_text("utf-8"))
        files = manifest["files"]
        self.docs: list[dict] = json.loads((data_dir / files["documents"]).read_text("utf-8"))
        self.vectors: np.ndarray = np.load(data_dir / files["embeddings"])
        if len(self.docs) != len(self.vectors):
            raise ValueError("documents.json and embeddings.npy are out of sync; rebuild index")

        self.model = TextEmbedding(
            manifest["embedding_model"],
            cache_dir=str(model_cache_dir) if model_cache_dir else None,
        )

        self.stemmer = Stemmer.Stemmer("english")
        self.bm25 = bm25s.BM25()
        self.bm25.index(self._tokenize([d["text"] for d in self.docs]), show_progress=False)

        # Normalized entity title -> indices of that entity's chunks.
        self.docs_by_title: dict[str, list[int]] = {}
        for i, d in enumerate(self.docs):
            self.docs_by_title.setdefault(normalize(d["title"]), []).append(i)
        self.titles = list(self.docs_by_title)
        self.vocabulary = {w for d in self.docs for w in normalize(d["text"]).split()}

    def _tokenize(self, texts: list[str]) -> list[list[str]]:
        return bm25s.tokenize(
            [normalize(t) for t in texts],
            stemmer=self.stemmer,
            return_ids=False,
            show_progress=False,
        )

    def _dense_ranking(self, query: str) -> list[int]:
        vector = next(iter(self.model.embed([query])))
        scores = self.vectors @ (vector / np.linalg.norm(vector))
        return np.argsort(-scores)[:CANDIDATES].tolist()

    def _bm25_ranking(self, query: str) -> list[int]:
        tokens = self._tokenize([query])
        if not tokens[0]:
            return []
        k = min(CANDIDATES, len(self.docs))
        indices, scores = self.bm25.retrieve(tokens, k=k, show_progress=False)
        return [int(i) for i, s in zip(indices[0], scores[0], strict=True) if s > 0]

    def mentioned_titles(self, query: str) -> set[str]:
        """Entity titles named in the query, tolerating typos ("pikachoo", "farfetchd").

        Any n-gram can match a title exactly, but only words absent from the corpus get
        typo correction: real words sit one edit away from names ("ground" -> Round).
        """
        words = normalize(query).split()
        found = set()
        for n in range(1, MAX_NAME_WORDS + 1):
            for i in range(len(words) - n + 1):
                gram_words = words[i : i + n]
                gram = " ".join(gram_words)
                if gram in self.docs_by_title:
                    found.add(gram)
                elif len(gram) >= MIN_FUZZY_LENGTH and not any(
                    w in self.vocabulary for w in gram_words
                ):
                    match = process.extractOne(
                        gram,
                        self.titles,
                        scorer=Levenshtein.distance,
                        score_cutoff=max(1, len(gram) // 4),
                    )
                    if match:
                        found.add(match[0])
        return found

    def search(self, query: str, k: int = 5, kinds: set[str] | None = None) -> list[Hit]:
        scores: dict[int, float] = {}
        for ranking in (self._dense_ranking(query), self._bm25_ranking(query)):
            for rank, i in enumerate(ranking):
                scores[i] = scores.get(i, 0.0) + 1 / (RRF_K + rank + 1)
        for title in self.mentioned_titles(query):
            for i in self.docs_by_title[title]:
                scores[i] = scores.get(i, 0.0) + NAME_BOOST

        hits: list[Hit] = []
        per_entity: dict[tuple[str, int], int] = {}
        for i, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
            doc = self.docs[i]
            entity = (doc["kind"], doc["entity_id"])
            if (kinds and doc["kind"] not in kinds) or per_entity.get(entity, 0) >= (
                MAX_CHUNKS_PER_ENTITY
            ):
                continue
            per_entity[entity] = per_entity.get(entity, 0) + 1
            hits.append(Hit(doc, score))
            if len(hits) == k:
                break
        return hits
