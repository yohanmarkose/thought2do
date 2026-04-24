"""Deduplication agent node.

Compares each newly extracted task against the user's existing tasks,
labels each as unique/duplicate/related, and recommends an action
(create/skip/merge/update/delete).
"""
import json
import logging
from typing import Any, Dict

from app.agents import invoke_json
from app.agents.state import AgentState
from app.prompts.dedup_prompt import DEDUP_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def dedup_node(state: AgentState) -> Dict[str, Any]:
    reasoning_log = list(state.get("reasoning_log", []))
    extracted = state.get("extracted_tasks", []) or []

    # No extracted tasks → nothing to dedupe.
    if not extracted:
        reasoning_log.append("[dedup] no extracted tasks to dedupe")
        return {"dedup_results": [], "reasoning_log": reasoning_log}

    existing_tasks_json = json.dumps(
        state.get("existing_tasks", []),
        default=str,
    )
    system_prompt = DEDUP_SYSTEM_PROMPT.format(
        existing_tasks=existing_tasks_json,
    )
    user_message = (
        "Newly extracted tasks (emit one result object per task in this order):\n"
        + json.dumps(extracted, default=str, indent=2)
    )

    try:
        parsed = await invoke_json(system_prompt, user_message)
    except Exception as exc:
        logger.exception("Dedup agent LLM call failed")
        reasoning_log.append(f"[dedup] ERROR: {exc}")
        return {
            "error": f"dedup_node: {exc}",
            "reasoning_log": reasoning_log,
        }

    results = parsed.get("results", []) or []
    if not isinstance(results, list):
        msg = f"Dedup agent returned non-list `results`: {type(results).__name__}"
        logger.warning(msg)
        reasoning_log.append(f"[dedup] ERROR: {msg}")
        return {"error": f"dedup_node: {msg}", "reasoning_log": reasoning_log}

    if len(results) != len(extracted):
        logger.warning(
            "Dedup agent returned %d results for %d extracted tasks",
            len(results),
            len(extracted),
        )

    statuses = [r.get("status") for r in results]
    reasoning_log.append(
        f"[dedup] classified {len(results)} task(s): {statuses}"
    )
    return {"dedup_results": results, "reasoning_log": reasoning_log}
