"""Tests for the LangGraph agent nodes.

Covers intent classification (10 cases), decomposition (5 cases),
deduplication (3 cases), and end-to-end pipeline (2 cases) per
PLAN.md Phase 14.

All LLM calls are mocked — deterministic and fast. Real accuracy
evaluation lives in evaluation.py.

Deviations from PLAN.md noted:
- Summary agent node (summary_node) is NEW — added to pipeline after
  execute; full-pipeline tests mock it alongside the other agents.
- AgentState carries `summary` and `suggestions` fields (new).
- decomposition_node uses `invoke_json_with_tools` (not `invoke_json`)
  because of the resolve_date / web_search tool loop.
- Full pipeline tests verify both the returned dict structure AND that
  tasks were persisted in the test MongoDB database.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.agents.dedup_agent import dedup_node
from app.agents.decomposition_agent import decomposition_node
from app.agents.intent_agent import intent_node
from app.agents.state import AgentState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(**kw) -> AgentState:
    """Return a minimal valid AgentState, overridable via kwargs."""
    base: AgentState = {
        "transcript": "",
        "user_id": str(ObjectId()),
        "existing_tasks": [],
        "intent": None,
        "extracted_tasks": [],
        "dedup_results": [],
        "final_tasks": [],
        "actions_taken": [],
        "reasoning_log": [],
        "current_datetime": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "summary": None,
        "suggestions": [],
    }
    base.update(kw)
    return base


def _task(title: str, **kw) -> dict:
    """Minimal decomposition task dict."""
    return {
        "title": title,
        "description": None,
        "category": kw.get("category", "General"),
        "priority": kw.get("priority", "Medium"),
        "deadline": kw.get("deadline", None),
        "tags": kw.get("tags", []),
        "action": kw.get("action", "create"),
        "update_target_id": kw.get("update_target_id", None),
        "update_fields": kw.get("update_fields", {}),
    }


# ---------------------------------------------------------------------------
# Intent Classification — 10 test cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("transcript,expected_intent", [
    ("remind me to buy milk",                                                    "CREATE"),
    ("forget about the groceries",                                               "DELETE"),
    ("push my meeting to next week",                                             "UPDATE"),
    ("what's due tomorrow",                                                      "QUERY"),
    ("add laundry and also mark my report as done",                              "MIXED"),
    ("I already finished the presentation",                                      "UPDATE"),
    ("actually never mind about that",                                           "DELETE"),
    ("I need to study for my exam and buy groceries and call mom",               "CREATE"),
    ("what do I have on my plate this week",                                     "QUERY"),
    ("hmm let me think",                                                         "CREATE"),
])
async def test_intent_classification(transcript, expected_intent):
    state = _state(transcript=transcript)
    with patch("app.agents.intent_agent.invoke_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "intent": expected_intent,
            "confidence": 0.95,
            "reasoning": "mocked",
            "sub_intents": [],
        }
        result = await intent_node(state)
    assert result["intent"] == expected_intent
    assert any("[intent]" in line for line in result["reasoning_log"])
    mock_llm.assert_called_once()


async def test_intent_node_invalid_response_returns_error():
    """If the LLM returns an unknown intent, the node sets `error`."""
    state = _state(transcript="test")
    with patch("app.agents.intent_agent.invoke_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"intent": "INVALID", "confidence": 0.5, "reasoning": ""}
        result = await intent_node(state)
    assert "error" in result


async def test_intent_node_llm_exception_returns_error():
    """If the LLM raises, the node captures the error without crashing."""
    state = _state(transcript="test")
    with patch("app.agents.intent_agent.invoke_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = RuntimeError("LLM timeout")
        result = await intent_node(state)
    assert "error" in result
    assert any("ERROR" in line for line in result["reasoning_log"])


# ---------------------------------------------------------------------------
# Decomposition — 5 test cases
# ---------------------------------------------------------------------------

async def test_decomposition_single_task():
    """Simple transcript yields exactly one extracted task."""
    state = _state(transcript="remind me to buy milk")
    mock_resp = {
        "tasks": [_task("Buy milk", category="Personal")],
        "reasoning": "Single personal errand.",
    }
    with patch(
        "app.agents.decomposition_agent.invoke_json_with_tools",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = mock_resp
        result = await decomposition_node(state)
    assert len(result["extracted_tasks"]) == 1
    assert result["extracted_tasks"][0]["title"] == "Buy milk"


async def test_decomposition_multi_task():
    """Compound utterance yields multiple extracted tasks."""
    state = _state(transcript="I need to buy groceries and call my dentist")
    mock_resp = {
        "tasks": [
            _task("Buy groceries", category="Personal"),
            _task("Call dentist", category="Health"),
        ],
        "reasoning": "Two separate errands.",
    }
    with patch(
        "app.agents.decomposition_agent.invoke_json_with_tools",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = mock_resp
        result = await decomposition_node(state)
    assert len(result["extracted_tasks"]) == 2
    titles = {t["title"] for t in result["extracted_tasks"]}
    assert "Buy groceries" in titles
    assert "Call dentist" in titles


async def test_decomposition_relative_date_preserved():
    """Decomposition passes through deadline resolved by `resolve_date`."""
    state = _state(transcript="remind me to submit my report by Friday")
    resolved_deadline = "2026-04-25T09:00:00+00:00"
    mock_resp = {
        "tasks": [_task("Submit report", category="Work", deadline=resolved_deadline)],
        "reasoning": "Work task with Friday deadline.",
    }
    with patch(
        "app.agents.decomposition_agent.invoke_json_with_tools",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = mock_resp
        result = await decomposition_node(state)
    assert result["extracted_tasks"][0]["deadline"] == resolved_deadline


async def test_decomposition_priority_keyword():
    """Urgency language maps to a high-priority task."""
    state = _state(transcript="urgently fix the production bug")
    mock_resp = {
        "tasks": [_task("Fix production bug", category="Work", priority="Critical")],
        "reasoning": "'Urgently' → Critical priority.",
    }
    with patch(
        "app.agents.decomposition_agent.invoke_json_with_tools",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = mock_resp
        result = await decomposition_node(state)
    assert result["extracted_tasks"][0]["priority"] in ("Critical", "High")


async def test_decomposition_vague_task_gets_clarification_tag():
    """Vague transcript produces a task tagged `needs_clarification`."""
    state = _state(transcript="handle that thing")
    mock_resp = {
        "tasks": [_task("Handle that thing", tags=["needs_clarification"])],
        "reasoning": "Vague — tagged for clarification.",
    }
    with patch(
        "app.agents.decomposition_agent.invoke_json_with_tools",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = mock_resp
        result = await decomposition_node(state)
    assert "needs_clarification" in result["extracted_tasks"][0]["tags"]


# ---------------------------------------------------------------------------
# Deduplication — 3 test cases
# ---------------------------------------------------------------------------

async def test_dedup_exact_duplicate_is_skipped():
    """A task whose title exactly matches an existing one gets `skip`."""
    existing_id = str(ObjectId())
    state = _state(
        extracted_tasks=[_task("Buy milk")],
        existing_tasks=[{
            "id": existing_id,
            "title": "Buy milk",
            "category": "Personal",
            "priority": "Medium",
            "status": "pending",
        }],
    )
    mock_resp = {
        "results": [{
            "task_index": 0,
            "status": "duplicate",
            "recommendation": "skip",
            "matched_existing_id": existing_id,
            "reason": "Exact title match.",
            "merge_fields": {},
        }]
    }
    with patch("app.agents.dedup_agent.invoke_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_resp
        result = await dedup_node(state)
    assert result["dedup_results"][0]["recommendation"] == "skip"


async def test_dedup_semantic_duplicate_recommends_merge():
    """A semantically similar task gets `related` / `merge` recommendation."""
    existing_id = str(ObjectId())
    state = _state(
        extracted_tasks=[_task("Get groceries")],
        existing_tasks=[{
            "id": existing_id,
            "title": "Buy groceries",
            "category": "Personal",
            "priority": "Medium",
            "status": "pending",
        }],
    )
    mock_resp = {
        "results": [{
            "task_index": 0,
            "status": "related",
            "recommendation": "merge",
            "matched_existing_id": existing_id,
            "reason": "Semantically equivalent.",
            "merge_fields": {},
        }]
    }
    with patch("app.agents.dedup_agent.invoke_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_resp
        result = await dedup_node(state)
    assert result["dedup_results"][0]["recommendation"] == "merge"


async def test_dedup_unique_task_recommends_create():
    """A novel task with no existing match gets `unique` / `create`."""
    state = _state(
        extracted_tasks=[_task("Learn Spanish")],
        existing_tasks=[{
            "id": str(ObjectId()),
            "title": "Buy groceries",
            "category": "Personal",
            "priority": "Medium",
            "status": "pending",
        }],
    )
    mock_resp = {
        "results": [{
            "task_index": 0,
            "status": "unique",
            "recommendation": "create",
            "matched_existing_id": None,
            "reason": "No related task found.",
            "merge_fields": {},
        }]
    }
    with patch("app.agents.dedup_agent.invoke_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_resp
        result = await dedup_node(state)
    assert result["dedup_results"][0]["recommendation"] == "create"


# ---------------------------------------------------------------------------
# Full pipeline — 2 end-to-end tests (all LLM calls mocked, real DB)
# ---------------------------------------------------------------------------

async def test_full_pipeline_create_persists_task(test_db):
    """CREATE intent: task appears in the response AND in MongoDB."""
    from app.agents.graph import process_voice_input

    user_id = str(ObjectId())

    with (
        patch("app.agents.intent_agent.invoke_json", new_callable=AsyncMock) as m_intent,
        patch(
            "app.agents.decomposition_agent.invoke_json_with_tools",
            new_callable=AsyncMock,
        ) as m_decomp,
        patch("app.agents.dedup_agent.invoke_json", new_callable=AsyncMock) as m_dedup,
        patch(
            "app.agents.prioritization_agent.invoke_json", new_callable=AsyncMock
        ) as m_prio,
        patch("app.agents.summary_agent.invoke_json", new_callable=AsyncMock) as m_summary,
    ):
        m_intent.return_value = {
            "intent": "CREATE",
            "confidence": 0.97,
            "reasoning": "test",
            "sub_intents": [],
        }
        m_decomp.return_value = {
            "tasks": [_task("Buy milk", category="Personal", priority="Medium")],
            "reasoning": "Simple errand.",
        }
        m_dedup.return_value = {
            "results": [{
                "task_index": 0,
                "status": "unique",
                "recommendation": "create",
                "matched_existing_id": None,
                "reason": "New task.",
                "merge_fields": {},
                # `task` key required by _build_eligible_tasks in prioritization_agent
                "task": _task("Buy milk", category="Personal", priority="Medium"),
            }]
        }
        m_prio.return_value = {
            "tasks": [{"task_index": 0, "new_priority": "Medium", "reasoning": "ok"}],
            "overall_reasoning": "Looks good.",
        }
        m_summary.return_value = {
            "summary": "Created 1 task: Buy milk.",
            "suggestions": ["What's due this week?"],
        }

        result = await process_voice_input("remind me to buy milk", user_id, test_db)

    # Response shape
    assert len(result["tasks_created"]) == 1
    assert result["tasks_created"][0]["title"] == "Buy milk"
    assert result["tasks_updated"] == []
    assert result["tasks_deleted"] == []
    # New fields (deviation from PLAN — summary agent added)
    assert result["summary"] != ""
    assert isinstance(result["suggestions"], list)

    # Task persisted in DB
    doc = await test_db.tasks.find_one({"user_id": user_id, "title": "Buy milk"})
    assert doc is not None, "Task should be persisted in MongoDB"
    assert doc["category"] == "Personal"


async def test_full_pipeline_mixed_create_and_update(test_db):
    """MIXED intent: one create + one update both reflected in response."""
    from app.agents.graph import process_voice_input

    user_id = str(ObjectId())
    existing_id = str(ObjectId())

    # Pre-insert the task to be updated
    from datetime import datetime, timezone
    await test_db.tasks.insert_one({
        "_id": __import__("bson").ObjectId(existing_id),
        "title": "Old report",
        "description": None,
        "category": "Work",
        "priority": "Medium",
        "deadline": None,
        "status": "pending",
        "tags": [],
        "source": "manual",
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    with (
        patch("app.agents.intent_agent.invoke_json", new_callable=AsyncMock) as m_intent,
        patch(
            "app.agents.decomposition_agent.invoke_json_with_tools",
            new_callable=AsyncMock,
        ) as m_decomp,
        patch("app.agents.dedup_agent.invoke_json", new_callable=AsyncMock) as m_dedup,
        patch(
            "app.agents.prioritization_agent.invoke_json", new_callable=AsyncMock
        ) as m_prio,
        patch("app.agents.summary_agent.invoke_json", new_callable=AsyncMock) as m_summary,
    ):
        m_intent.return_value = {
            "intent": "MIXED",
            "confidence": 0.9,
            "reasoning": "test",
            "sub_intents": ["CREATE", "UPDATE"],
        }
        m_decomp.return_value = {
            "tasks": [
                _task("Call dentist", category="Health", priority="Medium"),
                {
                    **_task("Old report", category="Work"),
                    "action": "update",
                    "update_target_id": existing_id,
                    "update_fields": {"priority": "High"},
                },
            ],
            "reasoning": "One new, one update.",
        }
        m_dedup.return_value = {
            "results": [
                {
                    "task_index": 0,
                    "status": "unique",
                    "recommendation": "create",
                    "matched_existing_id": None,
                    "reason": "New task.",
                    "merge_fields": {},
                    "task": _task("Call dentist", category="Health", priority="Medium"),
                },
                {
                    "task_index": 1,
                    "status": "unique",
                    "recommendation": "update",
                    "matched_existing_id": existing_id,
                    "reason": "Updating priority.",
                    "merge_fields": {},
                    "task": {
                        **_task("Old report", category="Work"),
                        "action": "update",
                        "update_target_id": existing_id,
                        "update_fields": {"priority": "High"},
                    },
                },
            ]
        }
        m_prio.return_value = {
            "tasks": [
                {"task_index": 0, "new_priority": "Medium", "reasoning": "ok"},
                {"task_index": 1, "new_priority": "High",   "reasoning": "ok"},
            ],
            "overall_reasoning": "Looks good.",
        }
        m_summary.return_value = {
            "summary": "Created 1 task and updated 1 task.",
            "suggestions": ["What else is pending?"],
        }

        result = await process_voice_input(
            "add dentist and mark old report as high priority", user_id, test_db
        )

    assert len(result["tasks_created"]) == 1
    assert result["tasks_created"][0]["title"] == "Call dentist"
    assert len(result["tasks_updated"]) == 1
    assert result["tasks_updated"][0]["title"] == "Old report"
    assert result["tasks_updated"][0]["priority"] == "High"
