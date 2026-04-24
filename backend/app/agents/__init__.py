"""LangGraph agent nodes and shared utilities.

Also hosts the `parse_llm_json()` helper (strips markdown code
fences and parses LLM JSON output) and `invoke_json()`, which runs
one LLM call with retry-once-on-parse-failure and a 30s timeout.
Both are used by every agent node.
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

_MODEL_NAME = "gpt-4o-mini"
_LLM_TIMEOUT_SECONDS = 30
_DEFAULT_RETRIES = 1  # 1 initial + 1 retry, per PLAN


def parse_llm_json(response_text: str) -> Dict[str, Any]:
    """Strip markdown code fences and parse JSON.

    Raises `ValueError` with the first 200 chars of the original
    response when parsing fails, for easier debugging.
    """
    if response_text is None:
        raise ValueError("Failed to parse LLM response: <None>")

    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json|JSON)?\s*", "", cleaned, count=1)
    if cleaned.endswith("```"):
        cleaned = re.sub(r"\s*```$", "", cleaned, count=1)
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse LLM response: {response_text[:200]}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Expected JSON object at top level, got {type(parsed).__name__}: "
            f"{response_text[:200]}"
        )
    return parsed


_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        settings = get_settings()
        _llm = ChatOpenAI(
            model=_MODEL_NAME,
            temperature=0,
            api_key=settings.OPENAI_API_KEY,
        )
    return _llm


async def invoke_json(
    system_prompt: str,
    user_message: str,
    *,
    retries: int = _DEFAULT_RETRIES,
) -> Dict[str, Any]:
    """Invoke GPT-4o-mini with a system/user pair; parse JSON reply.

    Retries once on parse failure or timeout (per PLAN). Raises
    `RuntimeError` if all attempts fail so the caller can write an
    error message into AgentState.
    """
    llm = _get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    last_error: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            response = await asyncio.wait_for(
                llm.ainvoke(messages),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
            raw = getattr(response, "content", None) or str(response)
            logger.debug(
                "LLM raw response (attempt %d/%d, len=%d): %s",
                attempt + 1,
                retries + 1,
                len(raw),
                raw[:500],
            )
            return parse_llm_json(raw)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "LLM call failed (attempt %d/%d): %s",
                attempt + 1,
                retries + 1,
                exc,
            )

    raise RuntimeError(
        f"LLM call failed after {retries + 1} attempts: {last_error}"
    )


async def invoke_json_with_tools(
    system_prompt: str,
    user_message: str,
    tools: Sequence[BaseTool],
    *,
    max_tool_iterations: int = 5,
    retries: int = _DEFAULT_RETRIES,
) -> Dict[str, Any]:
    """Invoke GPT-4o-mini with tool-calling, parse the final JSON reply.

    Loops while the LLM keeps requesting tool calls (up to
    `max_tool_iterations`), executing each tool and feeding the result
    back as a ToolMessage. When the LLM finally returns content with no
    tool calls, that content is parsed as JSON.

    Retries the whole exchange once on parse failure or timeout (per
    PLAN). Raises `RuntimeError` if all attempts fail so the caller can
    write an error message into AgentState.
    """
    tool_map = {t.name: t for t in tools}
    llm_with_tools = _get_llm().bind_tools(list(tools))

    last_error: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            messages: List[BaseMessage] = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]

            for iteration in range(max_tool_iterations):
                response = await asyncio.wait_for(
                    llm_with_tools.ainvoke(messages),
                    timeout=_LLM_TIMEOUT_SECONDS,
                )
                messages.append(response)

                tool_calls = getattr(response, "tool_calls", None) or []
                if not tool_calls:
                    raw = getattr(response, "content", None) or ""
                    logger.debug(
                        "Final LLM response (attempt %d/%d, iter %d, len=%d): %s",
                        attempt + 1,
                        retries + 1,
                        iteration,
                        len(raw),
                        raw[:500],
                    )
                    return parse_llm_json(raw)

                for tc in tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("args", {}) or {}
                    call_id = tc.get("id", "")
                    logger.debug("Tool call %s(%s)", name, args)

                    tool = tool_map.get(name)
                    if tool is None:
                        content = f"ERROR: unknown tool {name!r}"
                    else:
                        try:
                            content = await asyncio.to_thread(tool.invoke, args)
                        except Exception as tool_exc:
                            logger.exception("Tool %s raised", name)
                            content = f"ERROR: {tool_exc}"

                    messages.append(
                        ToolMessage(content=str(content), tool_call_id=call_id)
                    )
                    logger.debug("Tool %s → %s", name, str(content)[:200])
            else:
                raise RuntimeError(
                    f"Exceeded {max_tool_iterations} tool-call iterations"
                )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Tool-enabled LLM call failed (attempt %d/%d): %s",
                attempt + 1,
                retries + 1,
                exc,
            )

    raise RuntimeError(
        f"Tool-enabled LLM call failed after {retries + 1} attempts: {last_error}"
    )
