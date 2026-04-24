"""Task decomposition agent node.

Parses a transcript into structured task objects, resolves relative
dates against `current_datetime`, infers category and priority, and
tags UPDATE/DELETE/QUERY actions to existing tasks where applicable.
"""
import json
import logging
from typing import Any, Dict

from app.agents import invoke_json_with_tools
from app.agents.state import AgentState
from app.agents.tools import resolve_date, web_search
from app.prompts.decomposition_prompt import DECOMPOSITION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def decomposition_node(state: AgentState) -> Dict[str, Any]:
    existing_tasks_json = json.dumps(
        state.get("existing_tasks", []),
        default=str,
    )
    system_prompt = DECOMPOSITION_SYSTEM_PROMPT.format(
        existing_tasks=existing_tasks_json,
        current_datetime=state.get("current_datetime", ""),
    )

    intent = state.get("intent") or "CREATE"
    user_message = (
        f"Classified intent: {intent}\n"
        f"Transcript:\n{state['transcript']}"
    )

    reasoning_log = list(state.get("reasoning_log", []))

    try:
        parsed = await invoke_json_with_tools(
            system_prompt,
            user_message,
            tools=[resolve_date, web_search],
            # Enrichment asks may need several searches plus date
            # resolution across multiple tasks in one utterance.
            max_tool_iterations=8,
        )
    except Exception as exc:
        logger.exception("Decomposition agent LLM call failed")
        reasoning_log.append(f"[decomposition] ERROR: {exc}")
        return {
            "error": f"decomposition_node: {exc}",
            "reasoning_log": reasoning_log,
        }

    tasks = parsed.get("tasks", []) or []
    if not isinstance(tasks, list):
        msg = f"Decomposition agent returned non-list `tasks`: {type(tasks).__name__}"
        logger.warning(msg)
        reasoning_log.append(f"[decomposition] ERROR: {msg}")
        return {
            "error": f"decomposition_node: {msg}",
            "reasoning_log": reasoning_log,
        }

    reasoning = parsed.get("reasoning", "").strip() or "(no reasoning provided)"
    reasoning_log.append(
        f"[decomposition] extracted {len(tasks)} task(s): {reasoning}"
    )
    return {"extracted_tasks": tasks, "reasoning_log": reasoning_log}
