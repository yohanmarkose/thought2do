"""Settings page.

Sections: Profile, Appearance, Task Defaults, Voice Settings,
Data Management (export / clear completed / statistics), and About.
"""
import json
from collections import Counter
from datetime import datetime, timezone

import streamlit as st

from components.sidebar import render_sidebar
from utils.api_client import get_api_client
from utils.page import setup_page

_CATEGORIES = ["General", "Work", "Personal", "Health", "Finance", "Education"]
_PRIORITIES = ["Critical", "High", "Medium", "Low"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_dt(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _compute_stats(tasks):
    now    = datetime.now(timezone.utc)
    active = [t for t in tasks if t.get("status") not in ("completed", "cancelled")]
    return {
        "total_active": len(active),
        "due_today": sum(
            1 for t in active
            if (dt := _parse_dt(t.get("deadline"))) and dt.date() == now.date()
        ),
        "overdue": sum(
            1 for t in active
            if (dt := _parse_dt(t.get("deadline"))) and dt < now
        ),
        "completed_this_week": sum(
            1 for t in tasks
            if t.get("status") == "completed"
            and (dt := _parse_dt(t.get("updated_at")))
            and (now - dt).days < 7
        ),
    }


# ── Section renderers ─────────────────────────────────────────────────────────

def _render_profile(user):
    st.markdown("### 👤 Profile")
    c1, c2 = st.columns(2)
    c1.text_input("Name",  value=user.get("name",  ""), disabled=True, key="s_name")
    c2.text_input("Email", value=user.get("email", ""), disabled=True, key="s_email")
    dt = _parse_dt(user.get("created_at"))
    if dt:
        st.caption(f"Member since {dt.strftime('%B %d, %Y')}")


def _render_appearance():
    st.markdown("### 🎨 Appearance")
    current = st.session_state.get("theme", "dark")
    st.markdown(f"Current theme: **{'Dark 🌙' if current == 'dark' else 'Light ☀️'}**")
    label = "☀️ Switch to light mode" if current == "dark" else "🌙 Switch to dark mode"
    if st.button(label, use_container_width=True, key="settings_theme_toggle"):
        st.session_state.theme = "light" if current == "dark" else "dark"
        st.rerun()


def _render_task_defaults():
    st.markdown("### ⚙️ Task Defaults")
    st.caption("Pre-selected values when creating tasks manually on the Dashboard.")
    c1, c2 = st.columns(2)
    with c1:
        cur = st.session_state.get("default_category", "General")
        idx = _CATEGORIES.index(cur) if cur in _CATEGORIES else 0
        chosen = st.selectbox("Default Category", _CATEGORIES, index=idx, key="s_def_cat")
        if chosen != cur:
            st.session_state.default_category = chosen
            st.toast("✅ Default category saved!")
    with c2:
        cur = st.session_state.get("default_priority", "Medium")
        idx = _PRIORITIES.index(cur) if cur in _PRIORITIES else 2
        chosen = st.selectbox("Default Priority", _PRIORITIES, index=idx, key="s_def_prio")
        if chosen != cur:
            st.session_state.default_priority = chosen
            st.toast("✅ Default priority saved!")


def _render_voice_settings():
    st.markdown("### 🎙️ Voice Settings")
    try:
        _ = st.audio_input
        method = "Built-in microphone (`st.audio_input`)"
        detail = "Native browser audio capture is active (Streamlit ≥1.31)."
    except AttributeError:
        method = "File-upload fallback (`st.file_uploader`)"
        detail = "Upgrade Streamlit to ≥1.31 for native microphone support."
    st.markdown(f"**Active input method:** {method}")
    st.caption(detail)
    st.info(
        "Transcription: **OpenAI Whisper (whisper-1)**  \n"
        "Task extraction: **GPT-4o-mini** via LangGraph pipeline"
    )


def _render_data_management(client, tasks):
    st.markdown("### 🗄️ Data Management")

    # Export
    st.markdown("**Export**")
    if tasks:
        st.download_button(
            "📥 Export All Tasks (JSON)",
            data=json.dumps(tasks, indent=2, default=str),
            file_name=f"thought2do_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )
    else:
        st.info("No tasks to export yet.")

    st.divider()

    # Clear completed
    completed = [t for t in tasks if t.get("status") == "completed"]
    n = len(completed)
    st.markdown(f"**Clear Completed Tasks** — {n} completed task{'s' if n != 1 else ''}")

    if not completed:
        st.caption("Nothing to clear.")
    else:
        confirm_key = "confirm_clear_completed"
        if not st.session_state.get(confirm_key):
            if st.button("🧹 Clear Completed", use_container_width=True, key="clear_completed_btn"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            st.warning(f"Permanently delete all {n} completed tasks? This cannot be undone.")
            cc1, cc2, _ = st.columns([1.5, 1, 4])
            with cc1:
                if st.button("Confirm", use_container_width=True, key="confirm_clear_btn"):
                    errors = []
                    with st.spinner(f"Deleting {n} tasks…"):
                        for task in completed:
                            tid = task.get("id") or task.get("_id", "")
                            res = client.delete_task(tid)
                            if "error" in res:
                                errors.append(res["error"])
                    st.session_state.pop(confirm_key, None)
                    if errors:
                        st.error(f"Some deletions failed: {errors[0]}")
                    else:
                        st.toast(f"🧹 {n} completed tasks cleared!")
                    st.rerun()
            with cc2:
                if st.button("Cancel", use_container_width=True, key="cancel_clear_btn"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()

    st.divider()

    # Statistics
    st.markdown("**Statistics**")
    if not tasks:
        st.caption("No task data yet.")
        return

    total_created   = len(tasks)
    total_completed = sum(1 for t in tasks if t.get("status") == "completed")
    top_category    = Counter(t.get("category", "General") for t in tasks).most_common(1)[0][0]

    avg_per_day = "—"
    dates = [dt for t in tasks if (dt := _parse_dt(t.get("created_at")))]
    if dates:
        days = max(1, (datetime.now(timezone.utc) - min(dates)).days + 1)
        avg_per_day = f"{total_created / days:.1f}"

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Total Created",   total_created)
    s2.metric("Total Completed", total_completed)
    s3.metric("Top Category",    top_category)
    s4.metric("Avg Tasks / Day", avg_per_day)


def _render_about():
    st.markdown("### ℹ️ About")
    st.markdown("**Version:** 1.0.0")
    st.markdown(
        "| Component | Technology |\n"
        "|---|---|\n"
        "| Speech-to-text | OpenAI Whisper (whisper-1) |\n"
        "| Reasoning | GPT-4o-mini |\n"
        "| Agent pipeline | LangGraph |\n"
        "| Database | MongoDB Atlas |\n"
        "| Backend | FastAPI + Uvicorn |\n"
        "| Frontend | Streamlit |"
    )
    st.markdown("**Source:** [github.com/your-username/thought2do](#)")
    st.caption("Built for the Agentic AI course · Northeastern University · 2026.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    setup_page()
    client = get_api_client()
    user   = st.session_state.get("user") or {}

    with st.spinner("Loading…"):
        resp = client.get_tasks(limit=200)
    if "error" in resp:
        st.error(f"Could not load tasks: {resp['error']}")
        tasks = []
    else:
        tasks = resp.get("tasks", [])

    # Store stats so sidebar widget shows current counts.
    st.session_state["dashboard_stats"] = _compute_stats(tasks)
    render_sidebar()

    st.markdown("# ⚙️ Settings")
    st.divider()
    _render_profile(user)
    st.divider()
    _render_appearance()
    st.divider()
    _render_task_defaults()
    st.divider()
    _render_voice_settings()
    st.divider()
    _render_data_management(client, tasks)
    st.divider()
    _render_about()


main()
