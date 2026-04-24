"""User Pydantic schemas.

Defines UserRegister, UserLogin, UserResponse, and UserInDB matching
the canonical user data model in PLAN.md. Used by the auth router
and auth service for request validation and response shaping.
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime


class UserInDB(UserResponse):
    hashed_password: str
