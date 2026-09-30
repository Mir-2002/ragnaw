import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ragnaw.catalog import Catalog
from ragnaw.chat import Agent
from ragnaw.config import get_settings
from ragnaw.llm import LLMRouter
from ragnaw.rate_limit import RateLimiter
from ragnaw.retrieval import KnowledgeIndex
from ragnaw.routes import chat, health
from ragnaw.tools import ToolBox

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.index = app.state.tools = app.state.agent = None
    app.state.rate_limiter = RateLimiter(settings.chat_rate_limit, settings.chat_global_rate_limit)
    if (settings.data_dir / "manifest.json").is_file():
        app.state.index = KnowledgeIndex(settings.data_dir, settings.model_cache_dir)
        catalog = Catalog(settings.data_dir / "ragnaw.sqlite")
        app.state.tools = ToolBox(catalog, app.state.index)
    else:
        # Serve /health anyway so the frontend can tell "up but no data" from "down".
        logger.warning("No manifest.json in %s; run `ingest all`", settings.data_dir)

    if app.state.tools and settings.llm_providers:
        router = LLMRouter(
            settings.llm_providers, settings.llm_timeout_seconds, settings.max_answer_tokens
        )
        app.state.agent = Agent(
            router, app.state.tools, settings.max_tool_rounds, settings.max_tool_result_chars
        )
    elif not settings.llm_providers:
        logger.warning("No GROQ_API_KEY or GEMINI_API_KEY set; /chat is disabled")
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="RAGNaw API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "HEAD", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    return app


app = create_app()
