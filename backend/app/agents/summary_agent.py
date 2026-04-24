"""Summary / Response agent node.

Runs as the LAST node in the LangGraph pipeline. Consumes the
`actions_taken` log plus the original transcript/intent and produces a
conversational natural-language reply + a short list of suggestions
that the Assistant chat UI shows to the user.

Fails open: on LLM error, returns a deterministic fallback summary
built from the actions log so the UI never breaks.
"""
import json
import logging
from typing import Any, Dict, List

from app.agents import invoke_json
from app.agents.state import AgentState
from app.prompts.summary_prompt import SUMMARY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _slim_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a task dict to only the fields the Summary Agent reads."""
    if not isinstance(task, dict):
        return {}
    keep = ("id", "title", "description", "category", "priority", "deadline", "tags", "status")
    return {k: task.get(k) for k in keep if task.get(k) is not None}


def _collect_sections(actions: List[dict]) -> Dict[str, Any]:
    created: List[dict] = []
    updated: List[dict] = []
    deleted: List[dict] = []
    queried: List[dict] = []
    failures: List[dict] = []

    for a in actions or []:
        kind = a.get("action")
        if kind == "created" and a.get("task"):
            created.append(_slim_task(a["task"]))
        elif kind == "updated" and a.get("task"):
            updated.append(_slim_task(a["task"]))
        elif kind == "deleted":
            deleted.append({
                "id": a.get("task_id"),
                "title": a.get("title") or "",
            })
        elif kind == "queried":
            for t in a.get("tasks") or []:
                queried.append(_slim_task(t))
        elif kind == "failed":
            failures.append({
                "title": a.get("title") or "",
                "error": a.get("error") or "",
            })
    return {
        "tasks_created": created,
        "tasks_updated": updated,
        "tasks_deleted": deleted,
        "tasks_queried": queried,
        "failures": failures,
    }


def _fallback_summary(sections: Dict[str, Any], intent: str, transcript: str) -> Dict[str, Any]:
    """Deterministic summary used when the LLM call fails.

    Not as pretty as the LLM version, but keeps the UI usable."""
    created = sections["tasks_created"]
    updated = sections["tasks_updated"]
    deleted = sections["tasks_deleted"]
    queried = sections["tasks_queried"]
    failures = sections["failures"]

    parts: List[str] = []
    if created:
        titles = ", ".join(t.get("title", "") for t in created[:3] if t.get("title"))
        more = f" and {len(created) - 3} more" if len(created) > 3 else ""
        parts.append(
            f"I created {len(created)} task{'s' if len(created) != 1 else ''}: {titles}{more}."
        )
    if updated:
        titles = ", ".join(t.get("title", "") for t in updated[:3] if t.get("title"))
        more = f" and {len(updated) - 3} more" if len(updated) > 3 else ""
        parts.append(
            f"I updated {len(updated)} task{'s' if len(updated) != 1 else ''}: {titles}{more}."
        )
    if deleted:
        parts.append(
            f"I removed {len(deleted)} task{'s' if len(deleted) != 1 else ''}."
        )
    if queried:
        parts.append(
            f"You have {len(queried)} matching task{'s' if len(queried) != 1 else ''}."
        )
    if failures and not (created or updated or deleted):
        parts.append("I ran into an issue applying your request — take a look at the reasoning below.")
    if not parts:
        parts.append("I understood your request, but there was nothing to change.")

    suggestions: List[str] = []
    if created or updated:
        suggestions.append("What's due this week?")
    if queried:
        suggestions.append("Show me just the high-priority ones")
    if not suggestions:
        suggestions.append("What do I have coming up?")

    return {"summary": " ".join(parts), "suggestions": suggestions[:3]}


async def summary_node(state: AgentState) -> Dict[str, Any]:
    reasoning_log = list(state.get("reasoning_log", []))
    actions = state.get("actions_taken") or []
    intent = state.get("intent") or "CREATE"
    transcript = state.get("transcript") or ""

    sections = _collect_sections(actions)

    context_payload = {
        "transcript": transcript,
        "intent": intent,
        "existing_tasks_count": len(state.get("existing_tasks") or []),
        **sections,
    }

    user_message = (
        "Produce the chat reply for this pipeline run. Context:\n"
        + json.dumps(context_payload, default=str, indent=2)
    )

    try:
        parsed = await invoke_json(SUMMARY_SYSTEM_PROMPT, user_message)
    except Exception as exc:
        logger.warning("summary_node: LLM failed, using fallback: %s", exc)
        reasoning_log.append(f"[summary] LLM failed, used fallback: {exc}")
        fb = _fallback_summary(sections, intent, transcript)
        return {
            "summary": fb["summary"],
            "suggestions": fb["suggestions"],
            "reasoning_log": reasoning_log,
        }

    summary = (parsed.get("summary") or "").strip()
    suggestions = parsed.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = []
    # Keep only short string suggestions (defend against the LLM returning objects).
    suggestions = [s.strip() for s in suggestions if isinstance(s, str) and s.strip()][:3]

    if not summary:
        logger.warning("summary_node: empty summary, using fallback")
        fb = _fallback_summary(sections, intent, transcript)
        summary = fb["summary"]
        if not suggestions:
            suggestions = fb["suggestions"]

    reasoning_log.append(f"[summary] produced {len(suggestions)} suggestion(s)")
    return {
        "summary": summary,
        "suggestions": suggestions,
        "reasoning_log": reasoning_log,
    }
