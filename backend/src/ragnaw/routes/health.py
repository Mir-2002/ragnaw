from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ragnaw.config import Settings, get_settings

router = APIRouter()


# HEAD is included because most uptime monitors ping with HEAD by default.
@router.api_route("/health", methods=["GET", "HEAD"])
def health(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> dict:
    return {
        "status": "ok",
        "data_ready": request.app.state.index is not None,
        "llm_providers": [p.name for p in settings.llm_providers],
    }
