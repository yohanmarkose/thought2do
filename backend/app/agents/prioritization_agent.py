"""Prioritization agent node.

Validates/assigns priority for the final task set considering deadline
proximity and overall workload, and optionally flags existing tasks
for re-prioritization. Also finalises the per-task structure consumed
by the execute node: each final_tasks entry carries the task fields
plus `dedup_recommendation` and `update_target_id` (the id of an
existing task to update/delete when applicable).
"""
import json
import logging
from typing import Any, Dict, List

from app.agents import invoke_json
from app.agents.state import AgentState
from app.prompts.prioritization_prompt import PRIORITIZATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _build_eligible_tasks(dedup_results: List[dict]) -> List[dict]:
    """Carry dedup output forward, dropping skipped tasks.

    Keeps `merge_fields` in a dedicated `dedup_merge_fields` key so the
    execute node can apply exactly those fields on an `update_task` call
    without guessing which fields changed. The task dict itself is NOT
    mutated — preserving the original decomposition view.
    """
    eligible: List[dict] = []
    for r in dedup_results:
        recommendation = r.get("recommendation")
        if recommendation == "skip":
            continue

        task = dict(r.get("task") or {})
        matched_id = r.get("matched_existing_id")
        if matched_id and not task.get("update_target_id"):
            task["update_target_id"] = matched_id

        task["dedup_recommendation"] = recommendation
        task["dedup_merge_fields"] = r.get("merge_fields") or {}
        eligible.append(task)
    return eligible


async def prioritization_node(state: AgentState) -> Dict[str, Any]:
    reasoning_log = list(state.get("reasoning_log", []))
    dedup_results = state.get("dedup_results", []) or []
    eligible = _build_eligible_tasks(dedup_results)

    if not eligible:
        reasoning_log.append("[prioritization] no eligible tasks after dedup")
        return {"final_tasks": [], "reasoning_log": reasoning_log}

    # Give the LLM the merged view (task fields with merge_fields applied),
    # but strip our internal metadata. This lets the LLM reason about the
    # final deadline/priority as they will look post-merge, without leaking
    # dedup plumbing into its context.
    llm_inputs: List[dict] = []
    for t in eligible:
        merge_fields = t.get("dedup_merge_fields") or {}
        view = {
            k: v for k, v in t.items()
            if k not in (
                "dedup_recommendation",
                "dedup_merge_fields",
                "update_target_id",
                "update_fields",
            )
        }
        view.update(merge_fields)
        llm_inputs.append(view)

    system_prompt = PRIORITIZATION_SYSTEM_PROMPT.format(
        existing_tasks=json.dumps(state.get("existing_tasks", []), default=str),
        current_datetime=state.get("current_datetime", ""),
    )
    user_message = (
        "New tasks to validate priority for (one result object per task, same order):\n"
        + json.dumps(llm_inputs, default=str, indent=2)
    )

    try:
        parsed = await invoke_json(system_prompt, user_message)
    except Exception as exc:
        logger.exception("Prioritization agent LLM call failed")
        reasoning_log.append(f"[prioritization] ERROR: {exc}")
        # Fail-open: keep the incoming priorities so the pipeline can still execute.
        reasoning_log.append(
            "[prioritization] falling back to pre-prioritization priorities"
        )
        return {"final_tasks": eligible, "reasoning_log": reasoning_log}

    llm_tasks = parsed.get("tasks", []) or []
    if not isinstance(llm_tasks, list):
        logger.warning(
            "Prioritization agent returned non-list `tasks`: %s",
            type(llm_tasks).__name__,
        )
        llm_tasks = []

    # Apply new_priority index-aligned with eligible. Mismatched lengths
    # (rare) fall back to whatever priority the decomposition agent set.
    final_tasks: List[dict] = []
    for i, task in enumerate(eligible):
        merged = dict(task)
        if i < len(llm_tasks):
            new_priority = llm_tasks[i].get("new_priority")
            if new_priority in ("Critical", "High", "Medium", "Low"):
                merged["priority"] = new_priority
        final_tasks.append(merged)

    overall = parsed.get("overall_reasoning", "").strip() or "(no overall reasoning)"
    reasoning_log.append(
        f"[prioritization] finalised {len(final_tasks)} task(s): {overall}"
    )
    return {"final_tasks": final_tasks, "reasoning_log": reasoning_log}
