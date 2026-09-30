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
- Variables: `GROQ_MODEL`, `GEMINI_MODEL` (optional), `CORS_ORIGINS` (comma-separated, e.g. the Vercel URL)
