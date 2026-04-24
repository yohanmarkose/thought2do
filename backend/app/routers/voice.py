"""Voice router.

Exposes POST /voice/transcribe (audio upload → Whisper transcript)
and POST /voice/process (audio OR text transcript → LangGraph
multi-agent pipeline → DB operations → VoiceProcessResponse).
"""
import logging
from typing import Any, Dict, List

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
# Starlette's UploadFile is the BASE class of fastapi.UploadFile. When we
# call `request.form()` manually (as /voice/process does to support both
# multipart and JSON on the same path), Starlette emits its own UploadFile,
# not fastapi's subclass — so `isinstance(..., fastapi.UploadFile)` fails
# on a perfectly valid upload. Checking against the Starlette base class
# matches both kinds.
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.agents.graph import process_voice_input
from app.dependencies import get_current_user, get_database
from app.models.task import TaskResponse
from app.services.voice_service import VoiceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceProcessRequest(BaseModel):
    transcript: str


class VoiceProcessResponse(BaseModel):
    transcript: str
    tasks_created: List[TaskResponse] = []
    tasks_updated: List[TaskResponse] = []
    tasks_deleted: List[str] = []
    tasks_queried: List[TaskResponse] = []
    agent_reasoning: str = ""
    summary: str = ""
    suggestions: List[str] = []


def _get_service() -> VoiceService:
    return VoiceService()


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: VoiceService = Depends(_get_service),
) -> Dict[str, Any]:
    return await service.transcribe(file)


@router.post("/process", response_model=VoiceProcessResponse)
async def process(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: VoiceService = Depends(_get_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> VoiceProcessResponse:
    content_type = (request.headers.get("content-type") or "").lower()

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        file = form.get("file")
        if not isinstance(file, StarletteUploadFile):
            logger.warning(
                "voice/process multipart rejected: content_type=%r, form_keys=%s, "
                "file_value_type=%s",
                content_type,
                list(form.keys()),
                type(file).__name__ if file is not None else "None",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Multipart body must include a 'file' field containing audio. "
                    f"(received form keys: {list(form.keys())!r})"
                ),
            )
        transcription = await service.transcribe(file)
        transcript = transcription["transcript"]
    elif content_type.startswith("application/json"):
        body = await request.json()
        transcript = (body or {}).get("transcript", "")
        if not isinstance(transcript, str) or not transcript.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON body must include a non-empty 'transcript' string.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Content-Type must be multipart/form-data (with an audio file) or application/json (with a transcript).",
        )

    result = await process_voice_input(
        transcript=transcript,
        user_id=str(current_user["_id"]),
        db=db,
    )
    return VoiceProcessResponse(**result)
