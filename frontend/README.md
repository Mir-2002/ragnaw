# RAGNaw frontend

Next.js app that talks to the FastAPI backend directly (CORS) and streams answers over SSE.

```sh
pnpm install
cp .env.example .env.local
pnpm dev
```

Set `NEXT_PUBLIC_API_URL` in Vercel to the Space URL. It is inlined at build time, so
changing it requires a redeploy.
