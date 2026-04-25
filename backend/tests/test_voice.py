"""Tests for the voice router.

Mocks OpenAI Whisper (`VoiceService.transcribe`) and the full pipeline
(`process_voice_input`) to verify `/voice/transcribe` and
`/voice/process` return the expected response shapes without making
live network calls.

Deviations from PLAN.md noted:
- `/voice/process` now accepts either multipart (audio file) OR JSON
  body with `{"transcript": "..."}`.  Both paths are tested here.
- `VoiceProcessResponse` includes `summary` (str) and `suggestions`
  (List[str]) fields that the PLAN did not originally specify; tests
  assert their presence.
- `process_voice_input` is patched at the router import path so the
  full LangGraph pipeline never runs during unit tests.
"""
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_pipeline_result(transcript: str = "buy milk") -> dict:
    """Minimal VoiceProcessResponse-shaped dict returned by mocked pipeline."""
    return {
        "transcript": transcript,
        "tasks_created": [
            {
                "id": "000000000000000000000001",
                "title": "Buy milk",
                "description": None,
                "category": "Personal",
                "priority": "Medium",
                "deadline": None,
                "status": "pending",
                "tags": [],
                "parent_task_id": None,
                "source": "voice",
                "user_id": "000000000000000000000002",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ],
        "tasks_updated": [],
        "tasks_deleted": [],
        "tasks_queried": [],
        "agent_reasoning": "[intent] CREATE\n[decomposition] 1 task",
        # New fields added post-PLAN (summary agent)
        "summary": "I created 1 task: Buy milk.",
        "suggestions": ["What's due this week?"],
    }


# ---------------------------------------------------------------------------
# POST /voice/transcribe
# ---------------------------------------------------------------------------

def test_transcribe_returns_transcript(test_client, auth_headers):
    """POST /voice/transcribe with an audio file returns a transcript."""
    fake_audio = b"\x00" * 200  # Enough bytes to pass the size check

    with patch(
        "app.services.voice_service.VoiceService.transcribe",
        new_callable=AsyncMock,
    ) as mock_t:
        mock_t.return_value = {
            "transcript": "buy milk",
            "language": "en",
            "duration": 1.5,
        }
        r = test_client.post(
            "/voice/transcribe",
            files={"file": ("audio.webm", fake_audio, "audio/webm")},
            headers=auth_headers,
        )

    assert r.status_code == 200
    data = r.json()
    assert data["transcript"] == "buy milk"
    assert data["language"] == "en"


def test_transcribe_requires_auth(test_client):
    """POST /voice/transcribe without a token returns 401."""
    r = test_client.post(
        "/voice/transcribe",
        files={"file": ("audio.webm", b"\x00" * 200, "audio/webm")},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /voice/process — JSON transcript path
# ---------------------------------------------------------------------------

def test_process_json_transcript_returns_correct_structure(test_client, auth_headers):
    """POST /voice/process with JSON transcript returns full response shape."""
    with patch(
        "app.routers.voice.process_voice_input",
        new_callable=AsyncMock,
    ) as mock_pipeline:
        mock_pipeline.return_value = _mock_pipeline_result("buy milk")
        r = test_client.post(
            "/voice/process",
            json={"transcript": "buy milk"},
            headers=auth_headers,
        )

    assert r.status_code == 200
    data = r.json()
    assert data["transcript"] == "buy milk"
    assert isinstance(data["tasks_created"], list)
    assert isinstance(data["tasks_updated"], list)
    assert isinstance(data["tasks_deleted"], list)
    assert isinstance(data["tasks_queried"], list)
    assert isinstance(data["agent_reasoning"], str)
    # Verify new fields present (deviation from original PLAN)
    assert "summary" in data
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)


def test_process_json_empty_transcript_returns_400(test_client, auth_headers):
    """POST /voice/process with an empty transcript returns 400."""
    r = test_client.post(
        "/voice/process",
        json={"transcript": "   "},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_process_json_missing_transcript_returns_400(test_client, auth_headers):
    """POST /voice/process with no transcript key returns 400."""
    r = test_client.post(
        "/voice/process",
        json={"other_field": "value"},
        headers=auth_headers,
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /voice/process — multipart (audio) path
# ---------------------------------------------------------------------------

def test_process_audio_transcribes_then_runs_pipeline(test_client, auth_headers):
    """POST /voice/process with audio file: Whisper transcribes, pipeline runs."""
    fake_audio = b"\x00" * 200
    transcript_text = "remind me to call the dentist"

    with (
        patch(
            "app.services.voice_service.VoiceService.transcribe",
            new_callable=AsyncMock,
        ) as mock_t,
        patch(
            "app.routers.voice.process_voice_input",
            new_callable=AsyncMock,
        ) as mock_pipeline,
    ):
        mock_t.return_value = {
            "transcript": transcript_text,
            "language": "en",
            "duration": 2.0,
        }
        mock_pipeline.return_value = _mock_pipeline_result(transcript_text)

        r = test_client.post(
            "/voice/process",
            files={"file": ("audio.webm", fake_audio, "audio/webm")},
            headers=auth_headers,
        )

    assert r.status_code == 200
    data = r.json()
    assert data["transcript"] == transcript_text
    mock_t.assert_called_once()
    mock_pipeline.assert_called_once()


def test_process_unsupported_content_type_returns_415(test_client, auth_headers):
    """POST /voice/process with text/plain content-type returns 415."""
    r = test_client.post(
        "/voice/process",
        content=b"plain text body",
        headers={**auth_headers, "content-type": "text/plain"},
    )
    assert r.status_code == 415


def test_process_requires_auth(test_client):
    """POST /voice/process without a token returns 401."""
    r = test_client.post("/voice/process", json={"transcript": "test"})
    assert r.status_code == 401
