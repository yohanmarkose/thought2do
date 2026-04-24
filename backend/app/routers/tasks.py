"""Task CRUD router.

Exposes GET/POST /tasks, GET/PUT/DELETE /tasks/{id}. All endpoints
require a valid JWT (via `get_current_user`) and enforce user-scoped
access through the TaskService layer.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_current_user, get_database
from app.models.task import (
    CategoryType,
    PriorityType,
    StatusType,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_service(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> TaskService:
    return TaskService(db)


def _user_id(current_user: Dict[str, Any]) -> str:
    return str(current_user["_id"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_task(
    payload: TaskCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TaskService = Depends(_get_service),
) -> TaskResponse:
    return await service.create_task(payload, user_id=_user_id(current_user))


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[StatusType] = None,
    category: Optional[CategoryType] = None,
    priority: Optional[PriorityType] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TaskService = Depends(_get_service),
) -> TaskListResponse:
    return await service.get_tasks(
        user_id=_user_id(current_user),
        status=status,
        category=category,
        priority=priority,
        skip=skip,
        limit=limit,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TaskService = Depends(_get_service),
) -> TaskResponse:
    return await service.get_task(task_id, user_id=_user_id(current_user))


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TaskService = Depends(_get_service),
) -> TaskResponse:
    return await service.update_task(
        task_id,
        user_id=_user_id(current_user),
        updates=payload,
    )


@router.delete("/{task_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TaskService = Depends(_get_service),
) -> Response:
    await service.delete_task(task_id, user_id=_user_id(current_user))
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
