"""Voice recorder component.

Renders `st.audio_input` as the primary voice capture widget (Streamlit
1.31+), or falls back to `st.file_uploader` for older versions.

The widget key is versioned via `st.session_state.audio_reset_counter`
so the "🔄 Start over" button can fully reset the recorder by bumping
the counter — the next render instantiates a brand-new widget with
zero state instead of relying on `del st.session_state[key]`, which is
not always respected by media widgets.
"""
import streamlit as st

_ACCEPTED_EXTENSIONS = ["webm", "wav", "mp3", "m4a", "ogg", "mpeg"]


def audio_widget_key() -> str:
    """Return the current session-scoped key for the audio-input widget."""
    counter = st.session_state.get("audio_reset_counter", 0)
    return f"voice_audio_input_v{counter}"


def render_voice_recorder() -> None:
    """Render the recorder widget. Callers read bytes via
    `st.session_state[audio_widget_key()].getvalue()`."""
    key = audio_widget_key()
    if hasattr(st, "audio_input"):
        st.audio_input("🎙️ Record your thought", key=key)
    else:
        st.file_uploader(
            "Upload an audio file",
            type=_ACCEPTED_EXTENSIONS,
            key=key,
        )
