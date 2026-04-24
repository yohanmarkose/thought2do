"""LangGraph StateGraph assembly and `process_voice_input()` entry.

Wires the intent/decomposition/dedup/prioritization agents plus the
execution node into a compiled StateGraph, routes QUERY intents
directly to execute, and transforms the final state into a
VoiceProcessResponse payload for the voice router.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List

from langgraph.graph import END, START, StateGraph
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.dedup_agent import dedup_node
from app.agents.decomposition_agent import decomposition_node
from app.agents.intent_agent import intent_node
from app.agents.prioritization_agent import prioritization_node
from app.agents.state import AgentState
from app.models.task import TaskCreate, TaskUpdate
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)

ExecuteFn = Callable[[AgentState], Awaitable[Dict[str, Any]]]

_VALID_PRIORITIES = {"Critical", "High", "Medium", "Low"}


def _route_after_intent(state: AgentState) -> str:
    """Send QUERY intents straight to execute; everything else decomposes."""
    if state.get("intent") == "QUERY":
        return "execute"
    return "decomposition"


async def _run_create(
    service: TaskService,
    user_id: str,
    task: Dict[str, Any],
    actions: List[dict],
    reasoning_log: List[str],
) -> None:
    try:
        payload = TaskCreate(
            title=task.get("title") or "(untitled)",
            description=task.get("description"),
            category=task.get("category") or "General",
            priority=task.get("priority") or "Medium",
            deadline=task.get("deadline"),
            tags=task.get("tags") or [],
            parent_task_id=task.get("parent_task_id"),
            source="voice",
        )
        created = await service.create_task(payload, user_id=user_id)
        actions.append({
            "action": "created",
            "task_id": created.id,
            "title": created.title,
            "task": created.model_dump(mode="json"),
        })
    except Exception as exc:
        logger.exception("execute: create failed")
        actions.append({
            "action": "failed",
            "error": f"create: {exc}",
            "title": task.get("title", ""),
        })
        reasoning_log.append(f"[execute] create failed for '{task.get('title')}': {exc}")


async def _run_update(
    service: TaskService,
    user_id: str,
    task: Dict[str, Any],
    actions: List[dict],
    reasoning_log: List[str],
) -> None:
    target_id = task.get("update_target_id")
    if not target_id:
        reasoning_log.append(
            f"[execute] skipped update: no matched target for '{task.get('title')}'"
        )
        return

    recommendation = task.get("dedup_recommendation")
    if recommendation == "merge":
        raw_fields = dict(task.get("dedup_merge_fields") or {})
    else:
        raw_fields = dict(task.get("update_fields") or {})

    # If the prioritization agent changed priority, fold that in too.
    priority = task.get("priority")
    if priority in _VALID_PRIORITIES and "priority" not in raw_fields:
        raw_fields["priority"] = priority

    allowed = {"title", "description", "category", "priority", "deadline", "status", "tags"}
    fields = {k: v for k, v in raw_fields.items() if k in allowed and v is not None}
    if not fields:
        reasoning_log.append(
            f"[execute] skipped update: no fields to change for '{task.get('title')}'"
        )
        return

    try:
        updated = await service.update_task(target_id, user_id, TaskUpdate(**fields))
        actions.append({
            "action": "updated",
            "task_id": updated.id,
            "title": updated.title,
            "task": updated.model_dump(mode="json"),
        })
    except Exception as exc:
        logger.exception("execute: update failed")
        actions.append({
            "action": "failed",
            "error": f"update: {exc}",
            "task_id": target_id,
            "title": task.get("title", ""),
        })
        reasoning_log.append(f"[execute] update failed for id={target_id}: {exc}")


async def _run_delete(
    service: TaskService,
    user_id: str,
    task: Dict[str, Any],
    actions: List[dict],
    reasoning_log: List[str],
) -> None:
    target_id = task.get("update_target_id")
    if not target_id:
        reasoning_log.append(
            f"[execute] skipped delete: no matched target for '{task.get('title')}'"
        )
        return
    try:
        await service.delete_task(target_id, user_id)
        actions.append({
            "action": "deleted",
            "task_id": target_id,
            "title": task.get("title", ""),
        })
    except Exception as exc:
        logger.exception("execute: delete failed")
        actions.append({
            "action": "failed",
            "error": f"delete: {exc}",
            "task_id": target_id,
            "title": task.get("title", ""),
        })
        reasoning_log.append(f"[execute] delete failed for id={target_id}: {exc}")


async def _run_query(
    service: TaskService,
    user_id: str,
    task: Dict[str, Any],
    actions: List[dict],
    reasoning_log: List[str],
) -> None:
    filters = task.get("update_fields") or {}
    try:
        result = await service.get_tasks(
            user_id=user_id,
            status=filters.get("status"),
            category=filters.get("category"),
            priority=filters.get("priority"),
        )
        actions.append({
            "action": "queried",
            "count": len(result.tasks),
            "title": task.get("title", ""),
            "tasks": [t.model_dump(mode="json") for t in result.tasks],
        })
    except Exception as exc:
        logger.exception("execute: query failed")
        actions.append({
            "action": "failed",
            "error": f"query: {exc}",
            "title": task.get("title", ""),
        })
        reasoning_log.append(f"[execute] query failed: {exc}")


def _make_execute_node(db: AsyncIOMotorDatabase) -> ExecuteFn:
    async def execute_node(state: AgentState) -> Dict[str, Any]:
        actions_taken: List[dict] = list(state.get("actions_taken") or [])
        reasoning_log: List[str] = list(state.get("reasoning_log") or [])

        if state.get("error"):
            reasoning_log.append(
                f"[execute] aborted due to upstream error: {state['error']}"
            )
            return {"actions_taken": actions_taken, "reasoning_log": reasoning_log}

        service = TaskService(db)
        user_id = state["user_id"]
        intent = state.get("intent")
        final_tasks = state.get("final_tasks") or []

        # QUERY short-circuit path: intent -> execute with no decomposition.
        # No extracted filters, so return all active tasks for this user.
        if intent == "QUERY" and not final_tasks:
            try:
                result = await service.get_tasks(user_id=user_id)
                actions_taken.append({
                    "action": "queried",
                    "count": len(result.tasks),
                    "title": "(all active tasks)",
                    "tasks": [t.model_dump(mode="json") for t in result.tasks],
                })
                reasoning_log.append(
                    f"[execute] QUERY short-circuit returned {len(result.tasks)} task(s)"
                )
            except Exception as exc:
                logger.exception("execute: QUERY short-circuit failed")
                actions_taken.append({"action": "failed", "error": str(exc)})
                reasoning_log.append(f"[execute] QUERY short-circuit failed: {exc}")
            return {"actions_taken": actions_taken, "reasoning_log": reasoning_log}

        # Per-task dispatch for CREATE/UPDATE/DELETE/MIXED (and QUERY that went
        # through decomposition in some future variant).
        for task in final_tasks:
            if task.get("dedup_recommendation") == "skip":
                continue

            action = (task.get("action") or "create").lower()
            recommendation = task.get("dedup_recommendation")

            if recommendation == "merge" or action == "update":
                await _run_update(service, user_id, task, actions_taken, reasoning_log)
            elif action == "delete":
                await _run_delete(service, user_id, task, actions_taken, reasoning_log)
            elif action == "query":
                await _run_query(service, user_id, task, actions_taken, reasoning_log)
            elif action == "create":
                await _run_create(service, user_id, task, actions_taken, reasoning_log)
            else:
                reasoning_log.append(
                    f"[execute] unknown action {action!r} for '{task.get('title')}'"
                )

        reasoning_log.append(
            f"[execute] {sum(1 for a in actions_taken if a.get('action') != 'failed')} operation(s) completed"
        )
        return {"actions_taken": actions_taken, "reasoning_log": reasoning_log}

    return execute_node


def _build_graph(db: AsyncIOMotorDatabase):
    workflow = StateGraph(AgentState)
    workflow.add_node("intent", intent_node)
    workflow.add_node("decomposition", decomposition_node)
    workflow.add_node("dedup", dedup_node)
    workflow.add_node("prioritization", prioritization_node)
    workflow.add_node("execute", _make_execute_node(db))

    workflow.add_edge(START, "intent")
    workflow.add_conditional_edges(
        "intent",
        _route_after_intent,
        {"execute": "execute", "decomposition": "decomposition"},
    )
    workflow.add_edge("decomposition", "dedup")
    workflow.add_edge("dedup", "prioritization")
    workflow.add_edge("prioritization", "execute")
    workflow.add_edge("execute", END)
    return workflow.compile()


def _response_from_actions(
    transcript: str,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    tasks_created: List[dict] = []
    tasks_updated: List[dict] = []
    tasks_deleted: List[str] = []
    tasks_queried: List[dict] = []

    for action in state.get("actions_taken") or []:
        kind = action.get("action")
        if kind == "created" and action.get("task"):
            tasks_created.append(action["task"])
        elif kind == "updated" and action.get("task"):
            tasks_updated.append(action["task"])
        elif kind == "deleted" and action.get("task_id"):
            tasks_deleted.append(action["task_id"])
        elif kind == "queried":
            tasks_queried.extend(action.get("tasks") or [])

    reasoning_lines = state.get("reasoning_log") or []
    return {
        "transcript": transcript,
        "tasks_created": tasks_created,
        "tasks_updated": tasks_updated,
        "tasks_deleted": tasks_deleted,
        "tasks_queried": tasks_queried,
        "agent_reasoning": "\n".join(reasoning_lines),
    }


async def process_voice_input(
    transcript: str,
    user_id: str,
    db: AsyncIOMotorDatabase,
) -> Dict[str, Any]:
    """Run the multi-agent pipeline for a transcript and return a
    VoiceProcessResponse-shaped dict."""
    service = TaskService(db)
    existing = await service.get_tasks_for_context(user_id)

    initial_state: AgentState = {
        "transcript": transcript,
        "user_id": user_id,
        "existing_tasks": existing,
        "intent": None,
        "extracted_tasks": [],
        "dedup_results": [],
        "final_tasks": [],
        "actions_taken": [],
        "reasoning_log": [],
        "current_datetime": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

    graph = _build_graph(db)
    logger.info(
        "process_voice_input: user_id=%s transcript=%r existing=%d",
        user_id,
        transcript[:80],
        len(existing),
    )
    result = await graph.ainvoke(initial_state)
    return _response_from_actions(transcript, result)
