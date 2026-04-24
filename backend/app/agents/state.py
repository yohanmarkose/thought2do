"""AgentState TypedDict.

Defines the shared state object that flows through the LangGraph
pipeline: transcript, user_id, existing_tasks, intent, extracted_tasks,
dedup_results, final_tasks, actions_taken, reasoning_log,
current_datetime, error, and the final summary/suggestions produced
by the Summary Agent for the Assistant chat UI.
"""
from typing import List, Optional, TypedDict


class AgentState(TypedDict):
    transcript: str
    user_id: str
    existing_tasks: List[dict]
    intent: Optional[str]
    extracted_tasks: List[dict]
    dedup_results: List[dict]
    final_tasks: List[dict]
    actions_taken: List[dict]
    reasoning_log: List[str]
    current_datetime: str
    error: Optional[str]
    summary: Optional[str]
    suggestions: List[str]
