"""FastAPI shared dependencies.

Provides the module-level async MongoDB client (Motor), the
`get_database()` dependency, and the `get_current_user()` JWT-auth
dependency that decodes the Authorization Bearer token and returns
the matching user document from the `users` collection.
"""
import logging
from typing import Any, Dict, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

# Module-level singletons — the Motor client is safe to reuse across
# the process and maintains its own connection pool.
mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(_settings.MONGODB_URI)
database: AsyncIOMotorDatabase = mongo_client[_settings.MONGODB_DB_NAME]


async def get_database() -> AsyncIOMotorDatabase:
    return database


def _credentials_exception(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _credentials_exception("Missing or malformed Authorization header")

    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise _credentials_exception("Invalid or expired token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise _credentials_exception("Token missing subject claim")

    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError) as exc:
        raise _credentials_exception("Invalid user identifier") from exc

    user = await db.users.find_one({"_id": oid})
    if not user:
        raise _credentials_exception("User not found")

    return user
