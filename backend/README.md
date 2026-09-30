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

FastAPI backend for RAGNaw. The frontmatter above is the Hugging Face Space config; this
directory is pushed as the Space's repo root.

## Local development

```sh
uv sync
cp .env.example .env   # add GROQ_API_KEY and/or GEMINI_API_KEY
uv run uvicorn ragnaw.main:app --reload --port 7860
uv run pytest
```

## Space settings

- Secrets: `GROQ_API_KEY`, `GEMINI_API_KEY` (either may be left unset; Groq is tried first)
- Variables: `CORS_ORIGINS` (comma-separated, e.g. the Vercel URL). Optional:
  `GROQ_MODEL`, `GEMINI_MODEL`, `*_REASONING_EFFORT`, `CHAT_RATE_LIMIT`,
  `CHAT_GLOBAL_RATE_LIMIT` (see `.env.example`)

## API

- `GET|HEAD /health`: `{status, data_ready, llm_providers}`
- `POST /chat` with `{"question": "..."}`: Server-Sent Events, in order: `status`
  (per tool call), `token` (answer text), `sources`, `done`. A single `error` event
  replaces the rest if answering fails. Rejections happen before streaming: 422 (empty or
  too long), 429 with `Retry-After`, or 503 (no data or no LLM key).
