"""Assistant page — chat + voice interface.

This is the primary interaction surface: users type or speak, and the
agentic pipeline creates / updates / deletes / queries tasks. Voice is
ALWAYS transcribed to text first so the user can see (and edit) what
was actually sent before the pipeline runs.

Chat history is kept in `st.session_state.chat_messages` so the
conversation feels continuous. Each user turn is sent through the same
`/voice/process` pipeline the Demo tab uses.
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from components.task_card import render_deleted_card, render_task_card
from components.voice_recorder import audio_widget_key, render_voice_recorder
from utils.api_client import get_api_client
from utils.page import setup_page

setup_page()

# ── Session state ─────────────────────────────────────────────────────────────

st.session_state.setdefault("chat_messages", [])   # list[dict]
st.session_state.setdefault("pending_transcript", "")
st.session_state.setdefault("audio_reset_counter", 0)
st.session_state.setdefault("chat_input_draft", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_audio_bytes() -> Tuple[Optional[bytes], str]:
    widget = st.session_state.get(audio_widget_key())
    if widget is None:
        return None, "recording.webm"
    try:
        data = widget.getvalue()
    except Exception:
        return None, "recording.webm"
    if not isinstance(data, bytes) or len(data) < 100:
        return None, "recording.webm"
    filename = getattr(widget, "name", None) or "recording.webm"
    return data, filename


def _reset_audio_widget() -> None:
    st.session_state.audio_reset_counter = (
        st.session_state.get("audio_reset_counter", 0) + 1
    )


def _append(role: str, **payload) -> None:
    """Append a message to chat_messages. Payload keys depend on role."""
    entry = {"role": role, "ts": datetime.now().isoformat(), **payload}
    st.session_state.chat_messages.append(entry)


def _clear_chat() -> None:
    st.session_state.chat_messages = []
    st.session_state.pending_transcript = ""
    # Safe to set here — this runs as an on_click callback, before the
    # text_area widget for `chat_input_draft` is re-instantiated.
    st.session_state.chat_input_draft = ""
    _reset_audio_widget()


def _use_suggestion(phrase: str) -> None:
    """on_click callback — populates the chat input draft."""
    st.session_state.chat_input_draft = phrase


# ── Extract the assistant message text from the pipeline result ───────────────

def _assistant_text(result: Dict[str, Any]) -> str:
    """Return the backend's natural-language summary, with a safety fallback.

    The Summary Agent in the backend pipeline now produces a
    conversational reply (and suggestions) for every pipeline run.
    We only fall back to a hand-built line when the field is empty —
    which should only happen on upstream errors that short-circuit the
    pipeline before the summary node runs."""
    summary = (result.get("summary") or "").strip()
    if summary:
        return summary

    # Upstream error or totally empty pipeline — surface whatever hint we
    # have from the reasoning log so the user isn't staring at nothing.
    reasoning = result.get("agent_reasoning", "")
    match = re.search(r"\[intent\]\s+(.+)", reasoning)
    if match:
        return (
            "I understood your request, but nothing needed to change. "
            f"({match.group(1).strip()[:140]})"
        )
    return "I understood your request, but there was nothing to change."


# ── Run the pipeline for the current input ────────────────────────────────────

def _queue_submit() -> None:
    """on_click callback — stash the current draft for processing on rerun.

    Widget keys cannot be mutated after the widget renders on the same run,
    so we copy the draft into a non-widget slot and clear the widget here
    (safe, because this callback fires before the next render)."""
    draft = (st.session_state.get("chat_input_draft") or "").strip()
    st.session_state._pending_submit = draft
    st.session_state.chat_input_draft = ""
    st.session_state.pending_transcript = ""
    _reset_audio_widget()


def _submit(transcript: str) -> None:
    """Send a transcript through the pipeline and append both messages."""
    transcript = transcript.strip()
    if not transcript:
        return
    _append("user", text=transcript)

    client = get_api_client()
    with st.spinner("🤔 Thinking..."):
        result = client.process_voice(transcript=transcript)

    if "error" in result:
        _append("assistant", text=f"⚠️ Something went wrong: {result['error']}", error=True)
    else:
        _append(
            "assistant",
            text=_assistant_text(result),
            result=result,
        )


def _transcribe_pending() -> None:
    """Pull bytes from the audio widget → Whisper → fill pending_transcript."""
    audio_bytes, filename = _get_audio_bytes()
    if audio_bytes is None:
        st.warning("No recording detected yet — hit the mic, speak, and stop before transcribing.")
        return

    client = get_api_client()
    with st.spinner("🎙️ Transcribing audio..."):
        result = client.transcribe_audio(audio_bytes=audio_bytes, filename=filename)
    if "error" in result:
        st.error(f"Transcription failed: {result['error']}")
        return
    transcript = (result.get("transcript") or "").strip()
    if not transcript:
        st.warning("Transcription came back empty. Try recording again.")
        return
    st.session_state.pending_transcript = transcript
    _reset_audio_widget()
    st.toast("📝 Transcribed — review and send.")


# ── Render chat history ───────────────────────────────────────────────────────

def _render_chat_history() -> None:
    msgs = st.session_state.chat_messages
    if not msgs:
        st.markdown(
            """
            <div class="chat-empty">
                <div class="chat-empty-icon">💬</div>
                <div class="chat-empty-title">Ask me anything about your tasks</div>
                <div class="chat-empty-sub">
                    Try: <em>"Remind me to submit my paper by Friday"</em>,
                    <em>"What do I have due this week?"</em>, or
                    <em>"Mark the gym task as done"</em>.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    for msg_idx, msg in enumerate(msgs):
        role = msg.get("role")
        text = msg.get("text", "")
        if role == "user":
            with st.chat_message("user", avatar="🧑"):
                st.markdown(text)
        else:
            avatar = "⚠️" if msg.get("error") else "🤖"
            with st.chat_message("assistant", avatar=avatar):
                st.markdown(text)
                result = msg.get("result") or {}
                created = result.get("tasks_created") or []
                updated = result.get("tasks_updated") or []
                deleted = result.get("tasks_deleted") or []
                queried = result.get("tasks_queried") or []

                for t in created:
                    render_task_card(t, action="created")
                for t in updated:
                    render_task_card(t, action="updated")
                for tid in deleted:
                    render_deleted_card(tid)
                for t in queried:
                    render_task_card(t, action="queried")

                # Dynamic suggestions from the Summary Agent — only on the
                # most recent assistant message to avoid stale chips.
                suggestions = result.get("suggestions") or []
                is_latest = (msg_idx == len(msgs) - 1)
                if suggestions and is_latest:
                    st.caption("Try next")
                    chip_cols = st.columns(min(len(suggestions), 3))
                    for i, phrase in enumerate(suggestions[:3]):
                        with chip_cols[i]:
                            st.button(
                                phrase,
                                key=f"dyn_suggest_{msg_idx}_{i}",
                                use_container_width=True,
                                on_click=_use_suggestion,
                                args=(phrase,),
                            )

                reasoning = result.get("agent_reasoning", "")
                if reasoning:
                    with st.expander("🧠 How I thought about this"):
                        for line in reasoning.splitlines():
                            if line.strip():
                                st.markdown(f"- {line}")


# ── Page layout ───────────────────────────────────────────────────────────────

# Process any queued submission from the previous run's Send-button on_click
# callback. Done BEFORE rendering the chat history so new messages show up
# on this same render cycle rather than after an extra rerun.
_pending_submit = st.session_state.pop("_pending_submit", None)
if _pending_submit and _pending_submit.strip():
    _submit(_pending_submit)

st.markdown("# 💬 Assistant")
st.caption(
    "Type or speak to manage your tasks. Voice is transcribed first so you can "
    "review what gets sent."
)

# Top-right: Clear chat
top_right = st.columns([6, 1])[1]
with top_right:
    if st.session_state.chat_messages:
        st.button("🧹 Clear", use_container_width=True, on_click=_clear_chat, key="clear_chat_btn")

st.divider()

# Chat history area
chat_container = st.container()
with chat_container:
    _render_chat_history()

st.divider()

# Voice recorder + transcribe-only button
with st.expander("🎙️ Use your voice", expanded=False):
    st.caption("Record, then **Transcribe** to review the text before sending.")
    render_voice_recorder()
    tc1, tc2 = st.columns([3, 1])
    with tc1:
        if st.button(
            "📝 Transcribe recording",
            use_container_width=True,
            key="transcribe_btn",
            help="Convert your recording to text. You can edit it before sending.",
        ):
            _transcribe_pending()
    with tc2:
        if st.button(
            "🔄 Reset mic",
            use_container_width=True,
            key="reset_mic_btn",
            on_click=_reset_audio_widget,
        ):
            pass

# If we have a pending transcript from voice, show it as the draft
_pending = st.session_state.pending_transcript
if _pending and not st.session_state.chat_input_draft:
    st.session_state.chat_input_draft = _pending
    st.session_state.pending_transcript = ""

# Main text input + send
st.markdown("#### Your message")
draft_col, send_col = st.columns([6, 1])
with draft_col:
    st.text_area(
        label="Message",
        key="chat_input_draft",
        label_visibility="collapsed",
        placeholder="Ask a question or tell me what to do with your tasks…",
        height=90,
    )
with send_col:
    st.markdown("<div style='height:0.3rem;'></div>", unsafe_allow_html=True)
    st.button(
        "🚀 Send",
        use_container_width=True,
        type="primary",
        key="send_msg_btn",
        on_click=_queue_submit,
    )

# Quick suggestion chips — starter ideas, shown only for an empty chat.
# Once a conversation is going, the Summary Agent emits per-message
# suggestions attached to each assistant reply, which are more relevant.
if not st.session_state.chat_messages:
    st.caption("Quick ideas")
    suggestion_cols = st.columns(4)
    _SUGGESTIONS = [
        "What's due this week?",
        "Add: finish report by Friday (high priority)",
        "Add bullet points on how to prepare for a dentist appointment",
        "Show me all Work tasks",
    ]
    for i, phrase in enumerate(_SUGGESTIONS):
        with suggestion_cols[i]:
            st.button(
                phrase,
                key=f"suggest_{i}",
                use_container_width=True,
                on_click=_use_suggestion,
                args=(phrase,),
            )

