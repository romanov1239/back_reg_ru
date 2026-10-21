from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from rag_service import answer, is_configured, is_indexed, RagUnavailable

router = APIRouter(prefix="/rag", tags=["rag"])


class AskRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    answer: str
    sources: list[str]


class StatusResponse(BaseModel):
    configured: bool
    indexed: bool


@router.get("/")
def rag_page():
    """Страница с чатом. Открывается даже без ключа."""
    return FileResponse("static/assistant.html")


@router.get("/status", response_model=StatusResponse)
def rag_status():
    """Фронт спрашивает статус, чтобы показать баннер."""
    return {"configured": is_configured(), "indexed": is_indexed()}


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        return answer(req.text)
    except RagUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG error: {e}")
