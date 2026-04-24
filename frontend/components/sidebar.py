"""Sidebar component.

Renders the global sidebar: user identity, status/category/priority
filters, live stats (active/completed today/overdue), theme toggle,
backend connection indicator, and logout button.
"""
import streamlit as st

from utils.api_client import get_api_client


def render_sidebar() -> None:
    """Render the full sidebar with filters, stats, theme toggle, and logout."""
    user = st.session_state.get("user") or {}
    client = get_api_client()

    with st.sidebar:
        # User identity
        st.markdown(f"### 👤 {user.get('name', 'User')}")
        st.caption(user.get("email", ""))

        # Backend connection indicator
        health = client.health()
        if "error" in health:
            st.markdown("🔴 Backend offline")
        else:
            st.markdown("🟢 Backend connected")

        st.divider()

        # Filters — keys are bound directly to session_state
        st.markdown("**Filters**")
        st.selectbox(
            "Status",
            ["All", "pending", "in_progress", "completed", "cancelled"],
            key="filter_status",
        )
        st.selectbox(
            "Category",
            ["All", "Work", "Personal", "Health", "Finance", "Education", "General"],
            key="filter_category",
        )
        st.selectbox(
            "Priority",
            ["All", "Critical", "High", "Medium", "Low"],
            key="filter_priority",
        )

        st.divider()

        # Stats — populated by dashboard before render_sidebar() is called
        st.markdown("**Stats**")
        stats = st.session_state.get("dashboard_stats", {})
        c1, c2 = st.columns(2)
        c1.metric("Active", stats.get("total_active", "—"))
        c2.metric("Overdue", stats.get("overdue", "—"))
        st.caption(f"Completed this week: {stats.get('completed_this_week', '—')}")

        st.divider()

        # Theme toggle
        current = st.session_state.get("theme", "dark")
        label = "☀️ Switch to light" if current == "dark" else "🌙 Switch to dark"
        if st.button(label, use_container_width=True, key="sidebar_theme_toggle"):
            st.session_state.theme = "light" if current == "dark" else "dark"
            st.rerun()

        # Logout
        if st.button("🚪 Logout", use_container_width=True, key="sidebar_logout"):
            for key in ("token", "user"):
                st.session_state.pop(key, None)
            client.clear_token()
            st.rerun()
