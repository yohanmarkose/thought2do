"""Dashboard page — analytics + organised task views.

Four tabs:
  • Overview: headline metrics + quick distribution charts
  • By Priority: tasks grouped by priority (critical first)
  • By Category: tasks grouped by category
  • By Time: tasks bucketed by deadline (overdue, today, this week, …)

The Dashboard is read/organise oriented. Manual add/edit/delete stays
here; the Assistant tab is where natural-language CRUD happens.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import streamlit as st

from components.sidebar import render_sidebar
from components.task_card import render_task_card
from utils.api_client import get_api_client
from utils.page import setup_page

_PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
_PRIORITY_HEADERS = {
    "Critical": "🔴 Critical",
    "High":     "🟠 High",
    "Medium":   "🔵 Medium",
    "Low":      "⚪ Low",
}
_CATEGORIES = ["General", "Work", "Personal", "Health", "Finance", "Education"]
_CATEGORY_ICONS = {
    "Work":      "💼",
    "Personal":  "🏠",
    "Health":    "🏃",
    "Finance":   "💰",
    "Education": "📚",
    "General":   "📌",
}
_PRIORITIES = ["Critical", "High", "Medium", "Low"]
_STATUSES   = ["pending", "in_progress", "completed", "cancelled"]


# ── Parsing / bucket helpers ─────────────────────────────────────────────────

def _parse_dt(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_active(task: dict) -> bool:
    return task.get("status") not in ("completed", "cancelled")


def _is_overdue(task: dict) -> bool:
    if not _is_active(task):
        return False
    dt = _parse_dt(task.get("deadline"))
    return dt is not None and dt < datetime.now(timezone.utc)


def _is_due_today(task: dict) -> bool:
    if not _is_active(task):
        return False
    dt = _parse_dt(task.get("deadline"))
    return dt is not None and dt.date() == datetime.now(timezone.utc).date()


def _completed_this_week(task: dict) -> bool:
    if task.get("status") != "completed":
        return False
    dt = _parse_dt(task.get("updated_at"))
    return dt is not None and dt >= datetime.now(timezone.utc) - timedelta(days=7)


def _time_bucket(task: dict) -> str:
    """Return bucket key for 'By Time' grouping."""
    if not _is_active(task):
        return "Completed"
    dt = _parse_dt(task.get("deadline"))
    if dt is None:
        return "No deadline"
    now = datetime.now(timezone.utc)
    if dt < now and dt.date() != now.date():
        return "Overdue"
    if dt.date() == now.date():
        return "Today"
    if dt.date() == (now + timedelta(days=1)).date():
        return "Tomorrow"
    if dt <= now + timedelta(days=7):
        return "This week"
    return "Later"


_TIME_BUCKET_ORDER = ["Overdue", "Today", "Tomorrow", "This week", "Later", "No deadline", "Completed"]
_TIME_BUCKET_ICONS = {
    "Overdue":     "⚠️",
    "Today":       "📅",
    "Tomorrow":    "🌅",
    "This week":   "📆",
    "Later":       "🗓️",
    "No deadline": "⏳",
    "Completed":   "✅",
}


def _compute_stats(tasks: List[dict]) -> dict:
    active = [t for t in tasks if _is_active(t)]
    return {
        "total_active":        len(active),
        "due_today":           sum(1 for t in tasks if _is_due_today(t)),
        "overdue":             sum(1 for t in tasks if _is_overdue(t)),
        "completed_this_week": sum(1 for t in tasks if _completed_this_week(t)),
    }


def _apply_filters(tasks: List[dict]) -> List[dict]:
    status   = st.session_state.get("filter_status",   "All")
    category = st.session_state.get("filter_category", "All")
    priority = st.session_state.get("filter_priority", "All")
    out = tasks
    if status   != "All": out = [t for t in out if t.get("status")   == status]
    if category != "All": out = [t for t in out if t.get("category") == category]
    if priority != "All": out = [t for t in out if t.get("priority") == priority]
    return out


def _sort_tasks(tasks: List[dict], sort_by: str) -> List[dict]:
    if sort_by == "Deadline":
        return sorted(tasks, key=lambda t: t.get("deadline") or "9999")
    if sort_by == "Created Date":
        return sorted(tasks, key=lambda t: t.get("created_at") or "", reverse=True)
    return sorted(tasks, key=lambda t: _PRIORITY_ORDER.get(t.get("priority", "Medium"), 2))


def _task_id(task: dict) -> str:
    return task.get("id") or task.get("_id") or ""


# ── Add / edit / delete ──────────────────────────────────────────────────────

def _render_add_task_form(client) -> None:
    with st.expander("➕ Add Task", expanded=False):
        with st.form("add_task_form", clear_on_submit=True):
            title = st.text_input("Title *")
            description = st.text_area("Description", height=80)
            c1, c2 = st.columns(2)
            with c1:
                def_cat  = st.session_state.get("default_category", "General")
                def_prio = st.session_state.get("default_priority", "Medium")
                category = st.selectbox("Category", _CATEGORIES,
                                        index=_CATEGORIES.index(def_cat) if def_cat in _CATEGORIES else 0)
                priority = st.selectbox("Priority", _PRIORITIES,
                                        index=_PRIORITIES.index(def_prio) if def_prio in _PRIORITIES else 0)
            with c2:
                deadline_date = st.date_input("Deadline (optional)", value=None)
                tags_raw = st.text_input("Tags (comma-separated)")

            if st.form_submit_button("Create Task", use_container_width=True):
                if not title.strip():
                    st.error("Title is required.")
                else:
                    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
                    payload: dict = {
                        "title":       title.strip(),
                        "description": description.strip() or None,
                        "category":    category,
                        "priority":    priority,
                        "tags":        tags,
                        "source":      "manual",
                    }
                    if deadline_date:
                        payload["deadline"] = (
                            datetime.combine(deadline_date, datetime.min.time())
                            .replace(tzinfo=timezone.utc)
                            .isoformat()
                        )
                    result = client.create_task(payload)
                    if "error" in result:
                        st.error(f"Failed to create task: {result['error']}")
                    else:
                        st.toast("✅ Task created!")
                        st.rerun()


def _render_edit_form(task: dict, client) -> None:
    tid = _task_id(task)
    edit_key = f"show_edit_{tid}"

    with st.form(f"edit_form_{tid}"):
        title = st.text_input("Title", value=task.get("title", ""))
        description = st.text_area("Description", value=task.get("description") or "", height=80)
        c1, c2 = st.columns(2)
        with c1:
            cur_cat  = task.get("category", "General")
            category = st.selectbox("Category", _CATEGORIES,
                                    index=_CATEGORIES.index(cur_cat) if cur_cat in _CATEGORIES else 0)
            cur_prio = task.get("priority", "Medium")
            priority = st.selectbox("Priority", _PRIORITIES,
                                    index=_PRIORITIES.index(cur_prio) if cur_prio in _PRIORITIES else 2)
        with c2:
            cur_stat = task.get("status", "pending")
            status   = st.selectbox("Status", _STATUSES,
                                    index=_STATUSES.index(cur_stat) if cur_stat in _STATUSES else 0)

        sc, cc = st.columns(2)
        saved    = sc.form_submit_button("💾 Save",  use_container_width=True)
        canceled = cc.form_submit_button("Cancel",   use_container_width=True)

    if saved:
        updates = {
            "title":       title.strip(),
            "description": description.strip() or None,
            "category":    category,
            "priority":    priority,
            "status":      status,
        }
        result = client.update_task(tid, updates)
        if "error" in result:
            st.error(f"Update failed: {result['error']}")
        else:
            st.toast("✏️ Task updated!")
            st.session_state[edit_key] = False
            st.rerun()
    if canceled:
        st.session_state[edit_key] = False
        st.rerun()


def _render_task_with_actions(task: dict, client, *, key_prefix: str = "") -> None:
    tid         = _task_id(task)
    # key_prefix keeps button keys unique when the same task renders in
    # multiple tabs (e.g., a task appearing in both By-Priority and By-Time).
    u           = f"{key_prefix}_{tid}"
    confirm_key = f"confirm_delete_{u}"
    edit_key    = f"show_edit_{u}"
    is_done     = task.get("status") == "completed"

    render_task_card(task)

    if st.session_state.get(confirm_key):
        st.warning("⚠️ Delete this task? This cannot be undone.")
        cc1, cc2, _ = st.columns([1.4, 1, 4])
        with cc1:
            if st.button("Confirm Delete", key=f"confirm_del_{u}", use_container_width=True):
                result = client.delete_task(tid)
                st.session_state.pop(confirm_key, None)
                if "error" in result:
                    st.error(f"Delete failed: {result['error']}")
                else:
                    st.toast("🗑️ Task deleted!")
                    st.rerun()
        with cc2:
            if st.button("Cancel", key=f"cancel_del_{u}", use_container_width=True):
                st.session_state.pop(confirm_key, None)
                st.rerun()
    else:
        ac1, ac2, ac3, _ = st.columns([1, 1, 1, 3])
        with ac1:
            label = "↩️ Reopen" if is_done else "✅ Complete"
            if st.button(label, key=f"complete_{u}", use_container_width=True):
                new_status = "pending" if is_done else "completed"
                result = client.update_task(tid, {"status": new_status})
                if "error" in result:
                    st.error(f"Update failed: {result['error']}")
                else:
                    st.toast("↩️ Reopened!" if is_done else "✅ Marked complete!")
                    st.rerun()
        with ac2:
            if st.button("✏️ Edit", key=f"edit_toggle_{u}", use_container_width=True):
                st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                st.rerun()
        with ac3:
            if st.button("🗑️ Delete", key=f"delete_{u}", use_container_width=True):
                st.session_state[confirm_key] = True
                st.rerun()

    if st.session_state.get(edit_key, False):
        _render_edit_form(task, client)


# ── Analytics (distribution + progress) ──────────────────────────────────────

def _render_metric_cards(stats: dict) -> None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active Tasks",         stats["total_active"])
    m2.metric("Due Today",            stats["due_today"])
    overdue = stats["overdue"]
    m3.metric("⚠️ Overdue" if overdue > 0 else "Overdue", overdue)
    m4.metric("Completed This Week",  stats["completed_this_week"])


def _render_distribution_charts(tasks: List[dict]) -> None:
    active = [t for t in tasks if _is_active(t)]
    if not active:
        st.info("No active tasks yet — head to the Assistant tab to add some.")
        return

    c1, c2 = st.columns(2)

    # Priority distribution
    with c1:
        st.markdown("##### By Priority")
        prio_counts = Counter(t.get("priority", "Medium") for t in active)
        prio_data = {p: prio_counts.get(p, 0) for p in _PRIORITIES}
        st.bar_chart(prio_data, height=220, color="#6C63FF")

    # Category distribution
    with c2:
        st.markdown("##### By Category")
        cat_counts = Counter(t.get("category", "General") for t in active)
        cat_data = {c: cat_counts.get(c, 0) for c in _CATEGORIES if cat_counts.get(c, 0) > 0}
        if cat_data:
            st.bar_chart(cat_data, height=220, color="#00D68F")
        else:
            st.caption("No categories to chart.")


def _render_completion_progress(tasks: List[dict]) -> None:
    total = len(tasks)
    if total == 0:
        return
    completed = sum(1 for t in tasks if t.get("status") == "completed")
    pct = completed / total
    st.markdown(f"##### Overall progress — **{completed} / {total}** complete ({pct:.0%})")
    st.progress(pct)


def _render_time_summary(tasks: List[dict]) -> None:
    buckets = Counter(_time_bucket(t) for t in tasks)
    cols = st.columns(len(_TIME_BUCKET_ORDER))
    for col, bucket in zip(cols, _TIME_BUCKET_ORDER):
        icon = _TIME_BUCKET_ICONS[bucket]
        col.metric(f"{icon} {bucket}", buckets.get(bucket, 0))


# ── Tab renderers ────────────────────────────────────────────────────────────

def _render_overview_tab(tasks: List[dict], stats: dict) -> None:
    _render_metric_cards(stats)
    st.markdown(" ")
    _render_completion_progress(tasks)
    st.divider()
    _render_distribution_charts(tasks)
    st.divider()
    st.markdown("##### Deadline breakdown")
    _render_time_summary(tasks)


def _render_priority_tab(tasks: List[dict], client) -> None:
    if not tasks:
        st.info("No tasks match your filters.")
        return

    groups: Dict[str, List[dict]] = {p: [] for p in _PRIORITY_ORDER}
    for task in tasks:
        p = task.get("priority", "Medium")
        groups.setdefault(p, []).append(task)

    for priority, header in _PRIORITY_HEADERS.items():
        group = groups.get(priority, [])
        if not group:
            continue
        st.markdown(f"### {header}  · `{len(group)}`")
        for task in group:
            _render_task_with_actions(task, client, key_prefix="prio")


def _render_category_tab(tasks: List[dict], client) -> None:
    if not tasks:
        st.info("No tasks match your filters.")
        return

    groups: Dict[str, List[dict]] = defaultdict(list)
    for task in tasks:
        groups[task.get("category", "General")].append(task)

    # Show categories with tasks first, in a sensible order.
    ordered = [c for c in _CATEGORIES if c in groups] + [c for c in groups if c not in _CATEGORIES]
    for category in ordered:
        group = groups[category]
        icon = _CATEGORY_ICONS.get(category, "📌")
        st.markdown(f"### {icon} {category}  · `{len(group)}`")
        for task in group:
            _render_task_with_actions(task, client, key_prefix="cat")


def _render_time_tab(tasks: List[dict], client) -> None:
    if not tasks:
        st.info("No tasks match your filters.")
        return

    groups: Dict[str, List[dict]] = defaultdict(list)
    for task in tasks:
        groups[_time_bucket(task)].append(task)

    for bucket in _TIME_BUCKET_ORDER:
        group = groups.get(bucket)
        if not group:
            continue
        icon = _TIME_BUCKET_ICONS[bucket]
        st.markdown(f"### {icon} {bucket}  · `{len(group)}`")
        for task in group:
            _render_task_with_actions(task, client, key_prefix="time")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    setup_page()
    client = get_api_client()

    with st.spinner("Loading tasks..."):
        resp = client.get_tasks(limit=200)

    if "error" in resp:
        st.error(f"Could not load tasks: {resp['error']}")
        all_tasks: List[dict] = []
    else:
        all_tasks = resp.get("tasks", [])

    stats = _compute_stats(all_tasks)
    st.session_state["dashboard_stats"] = stats
    render_sidebar()

    # Header
    st.markdown("## 📊 Dashboard")
    st.caption(datetime.now().strftime("%A, %B %d, %Y"))

    # Manual controls (collapsed by default)
    top_cols = st.columns([3, 2, 2])
    with top_cols[0]:
        _render_add_task_form(client)
    with top_cols[1]:
        sort_by = st.selectbox(
            "Sort", ["Priority", "Deadline", "Created Date"],
            key="sort_by",
            label_visibility="collapsed",
        )
    with top_cols[2]:
        if st.button("🔄 Refresh", use_container_width=True, key="refresh_dash"):
            st.rerun()

    # Apply sidebar filters
    filtered = _apply_filters(all_tasks)
    sorted_tasks = _sort_tasks(filtered, sort_by)

    # Empty-state hint if nothing exists at all
    if not all_tasks:
        st.info(
            "No tasks yet! Head to the **Assistant** tab to talk to the app, "
            "or use **➕ Add Task** above to create one manually."
        )
        st.page_link("pages/2_Assistant.py", label="Open Assistant", icon="💬")
        return

    # Tabs
    tab_overview, tab_priority, tab_category, tab_time = st.tabs(
        ["📊 Overview", "🎯 By Priority", "📂 By Category", "⏰ By Time"]
    )
    with tab_overview:
        _render_overview_tab(all_tasks, stats)
    with tab_priority:
        _render_priority_tab(sorted_tasks, client)
    with tab_category:
        _render_category_tab(sorted_tasks, client)
    with tab_time:
        _render_time_tab(sorted_tasks, client)


main()
