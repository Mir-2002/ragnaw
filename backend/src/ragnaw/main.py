from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ragnaw.config import get_settings
from ragnaw.routes import health


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="RAGNaw API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "HEAD", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    return app


app = create_app()
