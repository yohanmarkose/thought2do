"""Task Pydantic schemas.

Defines TaskCreate, TaskUpdate, TaskResponse, and TaskListResponse
matching the canonical task data model in PLAN.md (category/priority/
status/source enums, optional deadline, parent_task_id for subtasks).
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

CategoryType = Literal[
    "Work",
    "Personal",
    "Health",
    "Finance",
    "Education",
    "General",
]
PriorityType = Literal["Critical", "High", "Medium", "Low"]
StatusType = Literal["pending", "in_progress", "completed", "cancelled"]
SourceType = Literal["voice", "manual", "decomposed"]


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: CategoryType = "General"
    priority: PriorityType = "Medium"
    deadline: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    parent_task_id: Optional[str] = None
    source: SourceType = "voice"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[CategoryType] = None
    priority: Optional[PriorityType] = None
    deadline: Optional[datetime] = None
    status: Optional[StatusType] = None
    tags: Optional[List[str]] = None


class TaskResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    category: CategoryType
    priority: PriorityType
    deadline: Optional[datetime] = None
    status: StatusType
    tags: List[str] = Field(default_factory=list)
    parent_task_id: Optional[str] = None
    source: SourceType
    user_id: str
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int
