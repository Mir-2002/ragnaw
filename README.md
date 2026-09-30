# RAGNaw

A RAG demo over [PokeAPI](https://pokeapi.co) data: hybrid retrieval (MiniLM + BM25) plus
LLM tool calling (Groq, falling back to Gemini Flash) over a structured SQLite DB, so questions like "fastest Fire types"
or "what beats Water/Ground?" are computed rather than guessed.

| Directory | What | Deployed to |
|---|---|---|
| `frontend/` | Next.js (App Router, Tailwind) | Vercel (root directory: `frontend`) |
| `backend/` | FastAPI: `/health`, and `/chat` over SSE | Render (Docker, free) |
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

Both services deploy from this GitHub repo.

**Backend (Render, free web service).** New → Web Service → this repo, then:

| Setting | Value |
|---|---|
| Language | Docker |
| Root Directory | `backend` (only changes under it trigger deploys) |
| Dockerfile Path | `Dockerfile` (relative to the root directory) |
| Instance Type | Free |
| Health Check Path | `/health` |
| Environment | `GROQ_API_KEY`, `GEMINI_API_KEY` (secrets); `CORS_ORIGINS` = the Vercel URL |

The container binds to `$PORT`, which Render sets. It needs about 233 MB of RAM at peak.

**Frontend (Vercel).** Import the repo with root directory `frontend` and set
`NEXT_PUBLIC_API_URL` to the Render URL (e.g. `https://ragnaw-backend.onrender.com`).
It's inlined at build time, so changing it needs a redeploy.

**Cold starts.** Free Render services spin down after 15 minutes without traffic and take
about a minute to wake; the UI shows a waking state meanwhile. A monitor pinging `/health`
more often than every 15 minutes keeps it awake. One service running all month (~744 h)
fits Render's 750 free hours per workspace.

Hugging Face Spaces was the original target, but Docker and Gradio Spaces now need a paid
plan; `scripts/deploy-backend.sh` still works for a PRO account.

---

Unofficial fan project. Pokémon © Nintendo, Game Freak, Creatures. Data from PokeAPI.
