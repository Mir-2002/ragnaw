from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from ragnaw.config import Settings, get_settings

router = APIRouter()


class ChatRequest(BaseModel):
    question: str


def accepted_question(
    body: ChatRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Everything that can reject a question, run before the stream (and its 200) starts."""
    if request.app.state.agent is None:
        raise HTTPException(503, "The Pokémon data or the LLM providers aren't configured.")
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Ask a question.")
    if len(question) > settings.max_question_chars:
        raise HTTPException(422, f"Keep questions under {settings.max_question_chars} characters.")

    client = request.client.host if request.client else "unknown"
    retry_after = request.app.state.rate_limiter.hit(client)
    if retry_after is not None:
        raise HTTPException(
            429,
            f"Too many questions; try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
    return question


@router.post("/chat", response_class=EventSourceResponse)
async def chat(
    request: Request, question: Annotated[str, Depends(accepted_question)]
) -> AsyncIterator[ServerSentEvent]:
    async for event in request.app.state.agent.answer(question):
        yield ServerSentEvent(event=event.name, data=event.data)
