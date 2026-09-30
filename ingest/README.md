# RAGNaw ingest

Offline pipeline that turns PokeAPI data into the files the backend serves from
`backend/data/`. It never runs on the Space.

```sh
uv sync
uv run ingest fetch          # pinned snapshot of PokeAPI's CSV tables -> .cache/csv/
uv run ingest build-db       # -> backend/data/ragnaw.sqlite
uv run ingest build-index    # -> backend/data/{documents.json,embeddings.npy,manifest.json}
uv run ingest all
```

The PokeAPI commit used is recorded in `.cache/csv/source.json`.

`build-index` embeds ~4k chunks (≤128 tokens each) with MiniLM via fastembed; it takes a few
minutes on CPU. The model is cached in `.cache/models/`.

`uv run pytest` checks known facts (types, forms, type chart, evolutions) against the built DB.
