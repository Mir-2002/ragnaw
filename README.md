# RAGNaw

A RAG demo over [PokeAPI](https://pokeapi.co) data: hybrid retrieval (MiniLM + BM25) plus
LLM tool calling (Groq, falling back to Gemini Flash) over a structured SQLite DB, so questions like "fastest Fire types"
or "what beats Water/Ground?" are computed rather than guessed.

| Directory | What | Deployed to |
|---|---|---|
| `frontend/` | Next.js (App Router, Tailwind) | Vercel (root directory: `frontend`) |
| `backend/` | FastAPI, serves `/health` and (soon) `/chat` over SSE | Hugging Face Space (Docker) |
| `ingest/` | Offline pipeline: PokeAPI CSVs → `backend/data/` | Runs locally, never deployed |

## Local development

Requires Node 20+, pnpm, and [uv](https://docs.astral.sh/uv/).

```sh
# data (once)
cd ingest && uv sync && uv run ingest all

# backend on :7860
cd backend && uv sync && cp .env.example .env && uv run uvicorn ragnaw.main:app --reload --port 7860

# frontend on :3000
cd frontend && pnpm install && cp .env.example .env.local && pnpm dev
```

## Deployment

**Backend (HF Space).** `backend/` is uploaded as the Space's repo root with the `hf` CLI,
which stores the binary files in `backend/data/` through Xet (a plain git push to the Space
rejects them):

```sh
uvx --from huggingface_hub hf auth login     # once
HF_SPACE=<user>/ragnaw sh scripts/deploy-backend.sh
```

The upload doesn't delete files on the Space, so remove renamed or deleted files there
by hand.

Set `GROQ_API_KEY` and `GEMINI_API_KEY` as Space secrets and `CORS_ORIGINS` to the Vercel URL.

**Frontend (Vercel).** Import the repo with root directory `frontend` and set
`NEXT_PUBLIC_API_URL` to `https://<user>-ragnaw.hf.space`.

**Keep-alive.** Free Spaces sleep after ~48h without traffic. A monitor pinging
`https://<user>-ragnaw.hf.space/health` once a day is enough (GET and HEAD both work).
Rebuilds and restarts still cause cold starts; the UI shows a waking state for those.

---

Unofficial fan project. Pokémon © Nintendo, Game Freak, Creatures. Data from PokeAPI.
