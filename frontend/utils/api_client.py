"""HTTP client for the Thought2Do FastAPI backend.

Implements the `APIClient` class covering every endpoint in PLAN.md
(auth, tasks, voice). Honours the `BACKEND_URL` env var for Docker
networking and falls back to `http://localhost:8000` for local dev.
All methods return the parsed JSON body on success, or a dict of
shape `{"error": "<message>"}` on any non-2xx / network failure.
"""
import io
import os
import sys
from typing import Any, Dict, Optional

import requests
import streamlit as st

_DEFAULT_TIMEOUT_SECONDS = 90  # voice/process can take a few seconds per agent


def _extract_error(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"

    detail = body.get("detail") if isinstance(body, dict) else body
    if isinstance(detail, list):
        parts = []
        for d in detail:
            if isinstance(d, dict):
                msg = d.get("msg") or str(d)
                loc = d.get("loc")
                parts.append(f"{'/'.join(map(str, loc))}: {msg}" if loc else msg)
            else:
                parts.append(str(d))
        detail = "; ".join(parts)
    elif detail is None:
        detail = str(body)
    return f"HTTP {response.status_code}: {detail}"


def _guess_audio_mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "webm": "audio/webm",
        "wav":  "audio/wav",
        "mp3":  "audio/mp3",
        "m4a":  "audio/m4a",
        "ogg":  "audio/ogg",
        "mpeg": "audio/mpeg",
    }.get(ext, "application/octet-stream")


class APIClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (
            base_url
            or "https://thought2do-backend-60836936585.us-central1.run.app"
            or "http://localhost:8000"
        ).rstrip("/")
        self.token: Optional[str] = None

    # ---- Token management ----

    def set_token(self, token: Optional[str]) -> None:
        self.token = token

    def clear_token(self) -> None:
        self.token = None

    def get_headers(self) -> Dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    # ---- Low-level ----

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
        files: Any = None,
        timeout: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                headers=self.get_headers(),
                json=json,
                params=params,
                files=files,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            return {"error": f"Network error: {exc}"}

        if response.status_code == 204:
            return {}
        if response.ok:
            try:
                return response.json()
            except ValueError:
                return {"error": "Backend returned non-JSON body"}
        return {"error": _extract_error(response)}

    # ---- Auth ----

    def register(self, email: str, password: str, name: str) -> Dict[str, Any]:
        return self._request("POST", "/auth/register", json={
            "email": email, "password": password, "name": name,
        })

    def login(self, email: str, password: str) -> Dict[str, Any]:
        return self._request("POST", "/auth/login", json={
            "email": email, "password": password,
        })

    def get_me(self) -> Dict[str, Any]:
        return self._request("GET", "/auth/me")

    # ---- Tasks ----

    def get_tasks(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        params = {"skip": skip, "limit": limit}
        if status:   params["status"] = status
        if category: params["category"] = category
        if priority: params["priority"] = priority
        return self._request("GET", "/tasks", params=params)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/tasks/{task_id}")

    def create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/tasks", json=data)

    def update_task(self, task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", f"/tasks/{task_id}", json=data)

    def delete_task(self, task_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/tasks/{task_id}")

    # ---- Voice ----

    def _build_audio_multipart(
        self,
        audio_bytes: bytes,
        filename: str,
    ) -> Dict[str, Any]:
        # Coerce to pure bytes (memoryview / bytearray would confuse the
        # multipart encoder). Wrap in a BytesIO so `requests` picks up
        # its length via tell() and emits a correct Content-Length header;
        # passing raw bytes has occasionally produced malformed multipart
        # bodies on Windows Python installs in testing.
        if isinstance(audio_bytes, (memoryview, bytearray)):
            audio_bytes = bytes(audio_bytes)
        buf = io.BytesIO(audio_bytes)
        buf.seek(0)
        mime = _guess_audio_mime(filename)
        print(
            f"[api_client] multipart upload: filename={filename!r}, "
            f"bytes={len(audio_bytes)}, mime={mime}",
            file=sys.stderr,
            flush=True,
        )
        return {"file": (filename, buf, mime)}

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
    ) -> Dict[str, Any]:
        files = self._build_audio_multipart(audio_bytes, filename)
        return self._request("POST", "/voice/transcribe", files=files)

    def process_voice(
        self,
        audio_bytes: Optional[bytes] = None,
        transcript: Optional[str] = None,
        filename: str = "audio.webm",
    ) -> Dict[str, Any]:
        if audio_bytes is not None:
            files = self._build_audio_multipart(audio_bytes, filename)
            return self._request("POST", "/voice/process", files=files)
        if transcript is not None:
            return self._request("POST", "/voice/process", json={"transcript": transcript})
        return {"error": "process_voice requires either audio_bytes or transcript"}

    # ---- Misc ----

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/")


def get_api_client() -> APIClient:
    """Return a session-state-cached APIClient, kept in sync with
    `st.session_state.token`."""
    if "api_client" not in st.session_state:
        st.session_state.api_client = APIClient()
    client: APIClient = st.session_state.api_client

    token = st.session_state.get("token")
    if token and client.token != token:
        client.set_token(token)
    elif not token and client.token:
        client.clear_token()
    return client
