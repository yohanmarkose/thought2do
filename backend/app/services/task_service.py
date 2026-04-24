"""Task service: MongoDB CRUD for the `tasks` collection.

Implements the `TaskService` class with async create/read/update/delete
operations, priority-aware sorting, and `get_tasks_for_context()` which
returns a simplified active-tasks view for injection into LLM prompts.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.task import (
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
)

# Aggregation stage that materialises a numeric priority rank
# (Critical=0, High=1, Medium=2, Low=3) and a `_has_deadline` key that
# sorts missing deadlines after present ones within each priority tier.
_PRIORITY_ORDER_STAGE: Dict[str, Any] = {
    "$addFields": {
        "_priority_order": {
            "$switch": {
                "branches": [
                    {"case": {"$eq": ["$priority", "Critical"]}, "then": 0},
                    {"case": {"$eq": ["$priority", "High"]}, "then": 1},
                    {"case": {"$eq": ["$priority", "Medium"]}, "then": 2},
                    {"case": {"$eq": ["$priority", "Low"]}, "then": 3},
                ],
                "default": 4,
            }
        },
        "_has_deadline": {
            "$cond": [{"$ifNull": ["$deadline", False]}, 0, 1]
        },
    }
}


def _task_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Task not found",
    )


def _coerce_oid(task_id: str) -> ObjectId:
    try:
        return ObjectId(task_id)
    except (InvalidId, TypeError):
        raise _task_not_found()


def _doc_to_response(doc: Dict[str, Any]) -> TaskResponse:
    return TaskResponse(
        id=str(doc["_id"]),
        title=doc["title"],
        description=doc.get("description"),
        category=doc["category"],
        priority=doc["priority"],
        deadline=doc.get("deadline"),
        status=doc["status"],
        tags=doc.get("tags", []),
        parent_task_id=doc.get("parent_task_id"),
        source=doc["source"],
        user_id=doc["user_id"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


class TaskService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self.collection = db.tasks

    async def create_task(self, task: TaskCreate, user_id: str) -> TaskResponse:
        now = datetime.now(timezone.utc)
        doc = task.model_dump()
        doc.update(
            {
                "user_id": user_id,
                "status": "pending",
                "created_at": now,
                "updated_at": now,
            }
        )
        result = await self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _doc_to_response(doc)

    async def get_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> TaskListResponse:
        query: Dict[str, Any] = {"user_id": user_id}
        if status:
            query["status"] = status
        if category:
            query["category"] = category
        if priority:
            query["priority"] = priority

        total = await self.collection.count_documents(query)

        pipeline: List[Dict[str, Any]] = [
            {"$match": query},
            _PRIORITY_ORDER_STAGE,
            {
                "$sort": {
                    "_priority_order": 1,
                    "_has_deadline": 1,
                    "deadline": 1,
                    "created_at": 1,
                }
            },
            {"$skip": skip},
            {"$limit": limit},
        ]

        tasks: List[TaskResponse] = []
        async for doc in self.collection.aggregate(pipeline):
            tasks.append(_doc_to_response(doc))
        return TaskListResponse(tasks=tasks, total=total)

    async def get_task(self, task_id: str, user_id: str) -> TaskResponse:
        oid = _coerce_oid(task_id)
        doc = await self.collection.find_one({"_id": oid, "user_id": user_id})
        if not doc:
            raise _task_not_found()
        return _doc_to_response(doc)

    async def update_task(
        self,
        task_id: str,
        user_id: str,
        updates: TaskUpdate,
    ) -> TaskResponse:
        oid = _coerce_oid(task_id)
        update_dict = updates.model_dump(exclude_unset=True)
        update_dict["updated_at"] = datetime.now(timezone.utc)

        result = await self.collection.find_one_and_update(
            {"_id": oid, "user_id": user_id},
            {"$set": update_dict},
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            raise _task_not_found()
        return _doc_to_response(result)

    async def delete_task(self, task_id: str, user_id: str) -> bool:
        oid = _coerce_oid(task_id)
        result = await self.collection.delete_one(
            {"_id": oid, "user_id": user_id}
        )
        if result.deleted_count == 0:
            raise _task_not_found()
        return True

    async def get_tasks_for_context(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        pipeline: List[Dict[str, Any]] = [
            {
                "$match": {
                    "user_id": user_id,
                    "status": {"$in": ["pending", "in_progress"]},
                }
            },
            _PRIORITY_ORDER_STAGE,
            {"$sort": {"_priority_order": 1, "_has_deadline": 1, "deadline": 1}},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "id": {"$toString": "$_id"},
                    "title": 1,
                    "category": 1,
                    "priority": 1,
                    "deadline": 1,
                    "status": 1,
                    "tags": 1,
                }
            },
        ]
        return [doc async for doc in self.collection.aggregate(pipeline)]
