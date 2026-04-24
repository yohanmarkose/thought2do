"""Shared page bootstrap for authenticated Streamlit pages.

Each file under `frontend/pages/` calls `setup_page()` at the top:
- bounces unauthenticated users back to the login landing page, and
- re-injects the theme CSS so sub-pages look consistent with app.py.
"""
import streamlit as st

from utils.theme import get_custom_css, get_theme


def setup_page() -> None:
    if not st.session_state.get("token"):
        st.warning("Please log in to continue.")
        st.page_link("app.py", label="Go to login", icon="🔒")
        st.stop()

    css = get_custom_css(get_theme())
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
