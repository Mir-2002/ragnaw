import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ragnaw.catalog import Catalog
from ragnaw.config import get_settings
from ragnaw.retrieval import KnowledgeIndex
from ragnaw.routes import health
from ragnaw.tools import ToolBox

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.index = app.state.tools = None
    if (settings.data_dir / "manifest.json").is_file():
        app.state.index = KnowledgeIndex(settings.data_dir, settings.model_cache_dir)
        catalog = Catalog(settings.data_dir / "ragnaw.sqlite")
        app.state.tools = ToolBox(catalog, app.state.index)
    else:
        # Serve /health anyway so the frontend can tell "up but no data" from "down".
        logger.warning("No manifest.json in %s; run `ingest all`", settings.data_dir)
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
    return app


app = create_app()
