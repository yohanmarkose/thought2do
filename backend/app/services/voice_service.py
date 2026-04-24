"""Voice service: OpenAI Whisper transcription wrapper.

Implements the `VoiceService` class which accepts uploaded audio
(webm/wav/mp3/m4a/ogg/mpeg), writes it to a temp file, invokes
Whisper, and returns `{transcript, language, duration}`.
"""
import logging
import os
import tempfile
from typing import Any, Dict

from fastapi import HTTPException, UploadFile, status
from openai import AsyncOpenAI, OpenAIError

from app.config import get_settings

logger = logging.getLogger(__name__)

_MAX_BYTES = 25 * 1024 * 1024  # Whisper's per-file limit

# whisper-1 must be explicitly enabled on your OpenAI project under
# Limits → Model permissions. verbose_json is only supported by whisper-1
# (the newer gpt-4o-*-transcribe models only support json/text).
_TRANSCRIPTION_MODEL = "whisper-1"
_TRANSCRIPTION_RESPONSE_FORMAT = "verbose_json"

_ALLOWED_EXTENSIONS = {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mpeg"}

_MIME_TO_SUFFIX: Dict[str, str] = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp3": ".mp3",
    "audio/mpeg": ".mp3",
    "audio/m4a": ".m4a",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/ogg": ".ogg",
    "application/ogg": ".ogg",
}


def _pick_suffix(upload: UploadFile) -> str:
    if upload.filename:
        ext = os.path.splitext(upload.filename)[1].lower()
        if ext in _ALLOWED_EXTENSIONS:
            return ext
    content_type = (upload.content_type or "").lower()
    if content_type in _MIME_TO_SUFFIX:
        return _MIME_TO_SUFFIX[content_type]
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            f"Unsupported audio format (filename={upload.filename!r}, "
            f"content_type={upload.content_type!r}). Allowed: webm, wav, mp3, m4a, ogg, mpeg."
        ),
    )


class VoiceService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def transcribe(self, audio_file: UploadFile) -> Dict[str, Any]:
        suffix = _pick_suffix(audio_file)

        data = await audio_file.read()
        if len(data) > _MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Audio file too large ({len(data)} bytes); Whisper limit is {_MAX_BYTES}.",
            )
        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty.",
            )

        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            tmp.write(data)
            tmp.close()

            with open(tmp.name, "rb") as fp:
                try:
                    response = await self.client.audio.transcriptions.create(
                        model=_TRANSCRIPTION_MODEL,
                        file=fp,
                        response_format=_TRANSCRIPTION_RESPONSE_FORMAT,
                    )
                except OpenAIError as exc:
                    logger.exception("Whisper transcription failed")
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Transcription service error: {exc}",
                    ) from exc

            return {
                "transcript": getattr(response, "text", "") or "",
                "language": getattr(response, "language", "unknown") or "unknown",
                "duration": float(getattr(response, "duration", 0.0) or 0.0),
            }
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                logger.warning("Failed to delete temp audio file: %s", tmp.name)
