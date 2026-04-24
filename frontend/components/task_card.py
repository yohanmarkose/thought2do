"""Task card component.

Renders a styled HTML card with a priority-coloured left border,
title (strikethrough if completed), category pill, priority badge,
deadline pill, source icon, status badge, and an optional
top-right "action" badge (created/updated/deleted/queried) used by
the voice-input results view.

Phase 10 implements the rendering surface; Phase 11 will extend this
module with inline complete/edit/delete interactions.
"""
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

_PRIORITY_CLASS = {
    "Critical": "task-card-critical",
    "High":     "task-card-high",
    "Medium":   "task-card-medium",
    "Low":      "task-card-low",
}
_PRIORITY_ICON = {
    "Critical": "🔴",
    "High":     "🟠",
    "Medium":   "🔵",
    "Low":      "⚪",
}
_SOURCE_ICON = {
    "voice":      "🎙️",
    "manual":     "✏️",
    "decomposed": "🔀",
}
# (label, background colour) keyed by pipeline action
_ACTION_BADGE = {
    "created": ("✅ Created", "#00D68F"),
    "updated": ("✏️ Updated", "#FFB547"),
    "deleted": ("🗑️ Deleted", "#FF6B6B"),
    "queried": ("👁️ Queried", "#6C63FF"),
}


def _description_to_html(text: str) -> str:
    """Convert plain text (with optional markdown-style bullet lines) to HTML."""
    lines = text.splitlines()
    html_parts = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue
        if stripped.startswith(("- ", "* ", "• ")):
            if not in_list:
                html_parts.append('<ul style="margin:0.3rem 0 0.3rem 1.2rem;padding:0;">')
                in_list = True
            item = stripped[2:]
            html_parts.append(f'<li style="margin-bottom:0.2rem;">{item}</li>')
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<p style="margin:0.2rem 0;">{stripped}</p>')
    if in_list:
        html_parts.append("</ul>")
    return "".join(html_parts)


def _format_deadline(iso_str: Optional[str]) -> Optional[str]:
    """Produce a short human-friendly deadline string; returns None if absent."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return iso_str[:16]

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = dt - now
    days = delta.days

    if dt.date() < now.date():
        return f"⚠️ Overdue ({dt.strftime('%b %d')})"
    if days == 0:
        return f"Due today ({dt.strftime('%H:%M')})"
    if days == 1:
        return "Due tomorrow"
    if 1 < days < 7:
        return f"Due in {days} days"
    return f"Due {dt.strftime('%b %d, %Y')}"


def render_task_card(task: dict, *, action: Optional[str] = None) -> None:
    """Render one task as an expandable HTML card. `action` surfaces a top-right badge."""
    title = task.get("title") or "(untitled)"
    priority = task.get("priority", "Medium")
    category = task.get("category", "General")
    source = task.get("source", "manual")
    status = task.get("status", "pending")
    deadline = _format_deadline(task.get("deadline"))
    tags = task.get("tags") or []
    description = task.get("description") or ""

    prio_class = _PRIORITY_CLASS.get(priority, "task-card-medium")
    prio_icon = _PRIORITY_ICON.get(priority, "🔵")
    source_icon = _SOURCE_ICON.get(source, "")

    title_style = (
        "font-weight:600;font-size:1rem;margin-bottom:0.4rem;"
        + ("text-decoration:line-through;opacity:0.6;" if status == "completed" else "")
    )

    action_html = ""
    if action in _ACTION_BADGE:
        label, colour = _ACTION_BADGE[action]
        action_html = (
            f'<span style="background:{colour};color:#fff;padding:2px 9px;'
            f'border-radius:999px;font-size:0.7rem;float:right;">{label}</span>'
        )

    deadline_html = (
        f'<span class="category-pill">📅 {deadline}</span>' if deadline else ""
    )
    tags_html = "".join(f'<span class="category-pill">#{t}</span>' for t in tags)

    status_class = f"badge-status-{status.replace('_', '-')}"

    desc_body = (
        f'<div style="color:#C9D1D9;">{_description_to_html(description)}</div>'
        if description else
        '<span style="color:#6B7785;font-style:italic;">No description</span>'
    )
    expand_section = (
        f'<div style="margin-top:0.6rem;padding-top:0.5rem;'
        f'border-top:1px solid rgba(255,255,255,0.08);font-size:0.85rem;">'
        f'{desc_body}'
        f'</div>'
    )

    html = (
        f'<div class="task-card {prio_class}">'
        f'<details>'
        f'<summary style="cursor:pointer;list-style:none;display:block;">'
        f'<style>summary::-webkit-details-marker{{display:none}}</style>'
        f'{action_html}'
        f'<div style="{title_style}">{source_icon} {title}'
        f'<span style="font-size:0.7rem;color:#8B949E;font-weight:400;margin-left:0.5rem;">▼ details</span>'
        f'</div>'
        f'<div>'
        f'<span class="category-pill">{category}</span>'
        f'<span class="badge badge-{priority.lower()}">{prio_icon} {priority}</span>'
        f'<span class="badge {status_class}">{status.replace("_", " ")}</span>'
        f'{deadline_html}{tags_html}'
        f'</div>'
        f'</summary>'
        f'{expand_section}'
        f'</details>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_deleted_card(task_id: str) -> None:
    """Placeholder card for a task that was deleted by the pipeline."""
    html = (
        f'<div class="task-card task-card-critical" style="opacity:0.75;">'
        f'<span style="background:#FF6B6B;color:#fff;padding:2px 9px;'
        f'border-radius:999px;font-size:0.7rem;float:right;">🗑️ Deleted</span>'
        f'<div style="color:#8B949E;font-family:monospace;">id: {task_id}</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
