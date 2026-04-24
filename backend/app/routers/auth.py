"""Authentication router.

Exposes POST /auth/register, POST /auth/login, and GET /auth/me,
delegating password hashing/JWT issuance to `services.auth_service`
and persisting users in the MongoDB `users` collection.
"""
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_current_user, get_database
from app.models.user import UserLogin, UserRegister, UserResponse
from app.services.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_doc_to_response(user_doc: Dict[str, Any]) -> UserResponse:
    return UserResponse(
        id=str(user_doc["_id"]),
        email=user_doc["email"],
        name=user_doc["name"],
        created_at=user_doc["created_at"],
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserRegister,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> UserResponse:
    existing = await db.users.find_one({"email": payload.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    doc = {
        "email": payload.email,
        "name": payload.name,
        "hashed_password": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _user_doc_to_response(doc)


@router.post("/login")
async def login(
    payload: UserLogin,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    user = await db.users.find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user_id=str(user["_id"]), email=user["email"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_doc_to_response(user),
    }


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> UserResponse:
    return _user_doc_to_response(current_user)
