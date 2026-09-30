---
title: RAGNaw API
emoji: ⚡
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# RAGNaw API

FastAPI backend for RAGNaw, deployed to Render as a Docker web service with this
directory as its root. (The frontmatter above only matters on a Hugging Face Space,
which now needs a paid plan for Docker.)

## Local development

```sh
uv sync
cp .env.example .env   # add GROQ_API_KEY and/or GEMINI_API_KEY
uv run uvicorn ragnaw.main:app --reload --port 7860
uv run pytest
```

## Environment (Render → Environment)

- Secrets: `GROQ_API_KEY`, `GEMINI_API_KEY` (either may be left unset; Groq is tried first)
- `CORS_ORIGINS` (comma-separated, e.g. the Vercel URL). Optional:
  `GROQ_MODEL`, `GROQ_FALLBACK_MODEL`, `GEMINI_MODEL`, `*_REASONING_EFFORT`, `CHAT_RATE_LIMIT`,
  `CHAT_GLOBAL_RATE_LIMIT` (see `.env.example`)

## API

- `GET|HEAD /health`: `{status, data_ready, llm_providers}`
- `POST /chat` with `{"question": "..."}`: Server-Sent Events, in order: `status`
  (per tool call), `token` (answer text), `sources`, `done`. A single `error` event
  replaces the rest if answering fails. Rejections happen before streaming: 422 (empty or
  too long), 429 with `Retry-After`, or 503 (no data or no LLM key).
