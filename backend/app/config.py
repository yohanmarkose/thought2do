"""Application configuration loader.

Uses pydantic-settings to load environment variables from the
project-root `.env`, exposing a cached `get_settings()` accessor.
Defines every key listed in the Environment Variables section of
PLAN.md, including optional Pinecone credentials which are allowed
to be `None`.
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# `.env` lives at the project root (thought2do/.env), but `make
# run-backend` runs from `backend/`. Resolve from __file__ so the
# file is found regardless of the process's current working dir.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "thought2do"
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 1440
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_INDEX_NAME: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
