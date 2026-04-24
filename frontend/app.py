"""Streamlit frontend entry point for Thought2Do.

Sets page config, injects the theme CSS, and gates access to the
multi-page app behind the login/register landing page. Initializes
shared `st.session_state` keys (token, user, theme, filters). Run via:

    streamlit run app.py --server.port 8501
"""
import streamlit as st

from components.auth_forms import render_login_form, render_register_form
from utils.api_client import get_api_client
from utils.theme import get_custom_css, get_theme

st.set_page_config(
    page_title="Thought2Do",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _init_session_state() -> None:
    defaults = {
        "token": None,
        "user": None,
        "theme": "dark",
        "filter_status": "All",
        "filter_category": "All",
        "filter_priority": "All",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _inject_theme() -> None:
    css = get_custom_css(get_theme())
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _render_landing() -> None:
    st.markdown(
        """
        <div class="landing-hero">
            <h1 class="landing-title">🧠 Thought2Do</h1>
            <p class="landing-tagline">Think it. Say it. Done.</p>
            <p class="landing-sub">
                Speak your tasks naturally. An agentic pipeline extracts them,
                deduplicates, prioritises, and saves them for you.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, middle, right = st.columns([1, 2, 1])
    with middle:
        login_tab, register_tab = st.tabs(["Login", "Create account"])
        with login_tab:
            render_login_form()
        with register_tab:
            render_register_form()


def _render_authenticated_sidebar() -> None:
    user = st.session_state.user or {}
    with st.sidebar:
        st.markdown(f"### 👤 {user.get('name', 'User')}")
        st.caption(user.get("email", ""))
        st.divider()

        st.markdown("**Appearance**")
        current = st.session_state.theme
        toggle_label = "☀️ Switch to light" if current == "dark" else "🌙 Switch to dark"
        if st.button(toggle_label, use_container_width=True, key="theme_toggle"):
            st.session_state.theme = "light" if current == "dark" else "dark"
            st.rerun()

        st.divider()
        if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
            for key in ("token", "user"):
                st.session_state.pop(key, None)
            get_api_client().clear_token()
            st.rerun()


def _render_authenticated_home() -> None:
    user = st.session_state.user or {}
    st.markdown(
        f"### Welcome back, {user.get('name', '')}! 👋"
    )
    st.markdown(
        "Use the sidebar to navigate to the **Dashboard**, **Voice Input**, or **Settings**."
    )

    # Quick backend health check so users know the API is reachable.
    health = get_api_client().health()
    if "error" in health:
        st.error(f"Backend connection issue: {health['error']}")
    else:
        st.success("Connected to the Thought2Do backend.")


def main() -> None:
    _init_session_state()
    _inject_theme()

    if not st.session_state.get("token"):
        _render_landing()
        return

    _render_authenticated_sidebar()
    _render_authenticated_home()


main()
