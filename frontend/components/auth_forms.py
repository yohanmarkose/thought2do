"""Authentication form components.

Provides `render_login_form()` and `render_register_form()` used by
the landing page. On success, stores token + user in session_state
and triggers `st.rerun()`.
"""
import streamlit as st

from utils.api_client import get_api_client


def _store_session(token: str, user: dict) -> None:
    st.session_state.token = token
    st.session_state.user = user


def render_login_form() -> None:
    with st.form("login_form", clear_on_submit=False):
        st.markdown("#### Login")
        email = st.text_input("Email", placeholder="you@example.com", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        submit = st.form_submit_button("Login", use_container_width=True, type="primary")

    if not submit:
        return

    if not email or not password:
        st.error("Email and password are required.")
        return

    client = get_api_client()
    with st.spinner("Signing in..."):
        resp = client.login(email, password)
    if "error" in resp:
        st.error(resp["error"])
        return

    _store_session(resp["access_token"], resp["user"])
    st.success(f"Welcome back, {resp['user'].get('name', email)}!")
    st.rerun()


def render_register_form() -> None:
    with st.form("register_form", clear_on_submit=False):
        st.markdown("#### Create your account")
        name = st.text_input("Name", placeholder="Your name", key="register_name")
        email = st.text_input("Email", placeholder="you@example.com", key="register_email")
        password = st.text_input(
            "Password",
            type="password",
            help="At least 8 characters.",
            key="register_password",
        )
        confirm = st.text_input(
            "Confirm password",
            type="password",
            key="register_password_confirm",
        )
        submit = st.form_submit_button(
            "Create account",
            use_container_width=True,
            type="primary",
        )

    if not submit:
        return

    if not all([name, email, password, confirm]):
        st.error("All fields are required.")
        return
    if len(password) < 8:
        st.error("Password must be at least 8 characters.")
        return
    if password != confirm:
        st.error("Passwords don't match.")
        return

    client = get_api_client()
    with st.spinner("Creating your account..."):
        reg_resp = client.register(email, password, name)
    if "error" in reg_resp:
        st.error(reg_resp["error"])
        return

    # Auto-login so the user lands in the authenticated shell immediately.
    with st.spinner("Signing in..."):
        login_resp = client.login(email, password)
    if "error" in login_resp:
        st.error(f"Account created, but auto-login failed: {login_resp['error']}")
        return

    _store_session(login_resp["access_token"], login_resp["user"])
    st.success(f"Welcome, {name}!")
    st.rerun()
