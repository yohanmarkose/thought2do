"""Intent classification agent node.

Classifies the primary intent of a transcript as one of
CREATE / UPDATE / DELETE / QUERY / MIXED and populates
`state["intent"]` plus a reasoning line.
"""
import json
import logging
from typing import Any, Dict

from app.agents import invoke_json
from app.agents.state import AgentState
from app.prompts.intent_prompt import INTENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_VALID_INTENTS = {"CREATE", "UPDATE", "DELETE", "QUERY", "MIXED"}


async def intent_node(state: AgentState) -> Dict[str, Any]:
    existing_tasks_json = json.dumps(
        state.get("existing_tasks", []),
        default=str,
    )
    system_prompt = INTENT_SYSTEM_PROMPT.format(
        existing_tasks=existing_tasks_json,
    )
    user_message = f"Transcript:\n{state['transcript']}"

    reasoning_log = list(state.get("reasoning_log", []))

    try:
        parsed = await invoke_json(system_prompt, user_message)
    except Exception as exc:
        logger.exception("Intent agent LLM call failed")
        reasoning_log.append(f"[intent] ERROR: {exc}")
        return {"error": f"intent_node: {exc}", "reasoning_log": reasoning_log}

    intent = parsed.get("intent")
    if intent not in _VALID_INTENTS:
        msg = f"Intent agent returned invalid intent: {intent!r}"
        logger.warning(msg)
        reasoning_log.append(f"[intent] ERROR: {msg}")
        return {"error": f"intent_node: {msg}", "reasoning_log": reasoning_log}

    reasoning = parsed.get("reasoning", "").strip() or "(no reasoning provided)"
    confidence = parsed.get("confidence")
    reasoning_log.append(
        f"[intent] {intent} (confidence={confidence}): {reasoning}"
    )
    return {"intent": intent, "reasoning_log": reasoning_log}
