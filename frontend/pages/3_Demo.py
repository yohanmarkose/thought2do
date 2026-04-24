"""Demo page.

Transparent showcase of the agentic pipeline: record audio or type a
transcript, then watch the Intent → Decomposition → Dedup →
Prioritization stages fire in sequence with the resulting task cards
and agent reasoning. Under the hood, the Assistant tab uses the same
pipeline — this page exposes its mechanics for demo purposes.
"""
import re
from typing import Optional, Tuple

import streamlit as st

from components.task_card import render_deleted_card, render_task_card
from components.voice_recorder import audio_widget_key, render_voice_recorder
from utils.api_client import get_api_client
from utils.page import setup_page

setup_page()

# ---- Page-local session state defaults ----
st.session_state.setdefault("voice_text_area", "")
st.session_state.setdefault("voice_result", None)
st.session_state.setdefault("audio_reset_counter", 0)


def _get_audio_data() -> Tuple[Optional[bytes], str]:
    """Read the current audio_input buffer as bytes.

    Returns `(bytes, filename)` if the widget has a recording of a sane
    size (>=100 bytes), else `(None, "recording.webm")`. The threshold
    rejects 0-byte / barely-there buffers that would make Whisper reject
    the request (and that have bitten us with 400s during testing).
    """
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


def _start_over() -> None:
    """Clear recording, typed text, and last result. Runs as an
    on_click callback so mutations happen before widgets re-render."""
    st.session_state.audio_reset_counter = (
        st.session_state.get("audio_reset_counter", 0) + 1
    )
    st.session_state.voice_text_area = ""
    st.session_state.voice_result = None


# ---- Pipeline-stage rendering ----
_STAGES = [
    ("intent",         "🎯 Intent Classification"),
    ("decomposition",  "🧩 Task Decomposition"),
    ("dedup",          "🔍 Deduplication"),
    ("prioritization", "⚖️ Prioritization"),
]


def _extract_stage_line(reasoning: str, tag: str) -> Optional[str]:
    match = re.search(rf"^\[{tag}\]\s+(.+?)$", reasoning, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def render_pipeline_stages(result: Optional[dict]) -> None:
    if result is None:
        for _, label in _STAGES:
            st.markdown(
                f'<div style="color:#8B949E;margin:0.3rem 0;">○ {label}</div>',
                unsafe_allow_html=True,
            )
        st.caption("Run a transcript to see the pipeline fire.")
        return

    reasoning = result.get("agent_reasoning", "")
    error_present = "[error]" in reasoning.lower() or "ERROR:" in reasoning

    for tag, label in _STAGES:
        line = _extract_stage_line(reasoning, tag)
        if line is None:
            icon = "⚠️"
            note = "stage skipped or no reasoning captured"
            colour = "#8B949E"
        else:
            icon = "✅"
            note = line
            colour = "#00D68F"
        snippet = note[:180] + ("…" if len(note) > 180 else "")
        st.markdown(
            f'<div style="margin:0.35rem 0;">'
            f'<span style="color:{colour};font-weight:600;">{icon} {label}</span>'
            f'<div style="color:#8B949E;font-size:0.78rem;margin-top:0.1rem;">{snippet}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    if error_present:
        st.warning("The pipeline reported an error — see the agent reasoning below.")


def render_results(result: dict) -> None:
    created = result.get("tasks_created") or []
    updated = result.get("tasks_updated") or []
    deleted = result.get("tasks_deleted") or []
    queried = result.get("tasks_queried") or []

    total = len(created) + len(updated) + len(deleted) + len(queried)
    st.markdown("### Results")
    if total == 0:
        st.info("Pipeline ran, but no tasks were created, updated, or deleted.")
        return
    for task in created:
        render_task_card(task, action="created")
    for task in updated:
        render_task_card(task, action="updated")
    for task_id in deleted:
        render_deleted_card(task_id)
    for task in queried:
        render_task_card(task, action="queried")


def render_reasoning_expander(result: dict) -> None:
    reasoning = result.get("agent_reasoning", "")
    if not reasoning:
        return
    with st.expander("🧠 Agent reasoning (chain of thought)"):
        for line in reasoning.splitlines():
            if line.strip():
                st.markdown(f"- {line}")


# ---- Page layout ----
st.markdown("# 🧪 Pipeline Demo")
st.caption("See the multi-agent pipeline in action — Intent → Decomposition → Dedup → Prioritization.")

col_left, col_right = st.columns([3, 2], gap="large")

with col_left:
    st.markdown("#### Record or type")
    render_voice_recorder()

    st.text_area(
        "Or type your thought here",
        placeholder="e.g., Remind me to submit my report by Friday...",
        key="voice_text_area",
        height=120,
    )

    # Read current buffers for the hint; audio still read fresh at click time.
    _audio_bytes, _ = _get_audio_data()
    if _audio_bytes is not None and st.session_state.voice_text_area.strip():
        st.caption("⚠️ Audio will take precedence over typed text.")

    btn_process_col, btn_reset_col = st.columns([3, 1])
    with btn_process_col:
        process_clicked = st.button(
            "🚀 Process",
            use_container_width=True,
            type="primary",
            key="voice_process_btn",
        )
    with btn_reset_col:
        st.button(
            "🔄 Start over",
            use_container_width=True,
            key="voice_reset_btn",
            on_click=_start_over,
            help="Clear the recording, typed text, and last result.",
        )

    if st.session_state.voice_result:
        with st.expander("Raw transcript"):
            st.write(st.session_state.voice_result.get("transcript", "") or "(empty)")

with col_right:
    st.markdown("#### Processing Pipeline")
    render_pipeline_stages(st.session_state.voice_result)
    if st.session_state.voice_result:
        render_results(st.session_state.voice_result)
        render_reasoning_expander(st.session_state.voice_result)


# ---- Process-button handler ----
if process_clicked:
    audio_bytes, audio_filename = _get_audio_data()
    text = st.session_state.voice_text_area.strip()

    if audio_bytes is None and not text:
        st.error("Record audio or type a transcript first.")
    else:
        client = get_api_client()
        with st.spinner("🤔 Thinking..."):
            if audio_bytes is not None:
                result = client.process_voice(
                    audio_bytes=audio_bytes,
                    filename=audio_filename,
                )
            else:
                result = client.process_voice(transcript=text)

        if "error" in result:
            st.error(f"Processing failed: {result['error']}")
        else:
            st.session_state.voice_result = result
            st.toast("✅ Tasks processed!")
            st.rerun()


# ---- Quick-action examples ----
st.divider()
st.markdown("#### Quick examples")
st.caption("Click a phrase to populate the text area, then press 🚀 Process.")

_QUICK_ACTIONS = [
    "Remind me to submit my project by Friday, it's urgent",
    "I need to buy groceries and also call the dentist",
    "Mark my gym task as done",
    "What's on my plate this week?",
]


def _set_text_area(value: str) -> None:
    # Runs as an `on_click` callback, which Streamlit invokes BEFORE
    # widgets are instantiated on the next run — so modifying the
    # widget's session-state key here is legal, unlike doing it from
    # a normal button-return branch after the widget has rendered.
    st.session_state.voice_text_area = value


cols = st.columns(len(_QUICK_ACTIONS))
for i, phrase in enumerate(_QUICK_ACTIONS):
    with cols[i]:
        st.button(
            phrase,
            key=f"quick_action_{i}",
            use_container_width=True,
            on_click=_set_text_area,
            args=(phrase,),
        )
