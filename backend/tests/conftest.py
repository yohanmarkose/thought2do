"""Shared pytest fixtures.

Provides `test_db` (isolated `thought2do_test` database), `test_client`
(FastAPI TestClient with test-db override), `auth_token` / `auth_headers`
(pre-registered user JWT), and `sample_tasks` (seeded task data) fixtures.

Deviations from PLAN.md noted here:
- `auth_headers` fixture added (convenience wrapper around `auth_token`).
- Session-scoped Motor client created at module level so TestClient's
  anyio event loop and the Motor pool share the same connection.
"""
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from starlette.testclient import TestClient

from app.config import get_settings
from app.dependencies import get_database
from app.main import app

_TEST_DB_NAME = "thought2do_test"

# Resolve MongoDB URI from the same .env the app uses, so tests run
# against the same Atlas cluster (or local instance) as production.
_TEST_MONGO_URI = get_settings().MONGODB_URI


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _clean_test_db():
    """Drop the test database before and after the full test session."""
    sync = MongoClient(_TEST_MONGO_URI)
    sync.drop_database(_TEST_DB_NAME)
    yield
    sync.drop_database(_TEST_DB_NAME)
    sync.close()


@pytest.fixture
def test_db(_clean_test_db):
    """Motor database for *async* pytest tests (test_agents full-pipeline).

    Function-scoped (default) so each async test gets a fresh Motor client
    in its own event loop.  A session-scoped client causes 'Event loop is
    closed' errors when the second async test runs in a different loop than
    the first.
    """
    client = AsyncIOMotorClient(_TEST_MONGO_URI)
    yield client[_TEST_DB_NAME]


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_client(_clean_test_db):
    """FastAPI TestClient with `get_database` overridden to a dedicated Motor
    client that is created lazily inside TestClient's own anyio event loop.

    This client is intentionally separate from the `test_db` fixture's client
    to avoid 'Event loop is closed' errors when async agent tests run first.
    """
    _db_holder: dict = {}

    async def _override():
        # Lazily create the Motor client the first time a request arrives,
        # which is guaranteed to be inside TestClient's anyio event loop.
        if "db" not in _db_holder:
            _db_holder["db"] = AsyncIOMotorClient(_TEST_MONGO_URI)[_TEST_DB_NAME]
        return _db_holder["db"]

    app.dependency_overrides[get_database] = _override
    # raise_server_exceptions=False lets us inspect 4xx/5xx bodies in tests.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

_TEST_USER = {
    "email": "testuser@example.com",
    "password": "TestPass123!",
    "name": "Test User",
}


@pytest.fixture(scope="session")
def auth_token(test_client):
    """Register test user (idempotent) and return a valid JWT string."""
    test_client.post("/auth/register", json=_TEST_USER)
    r = test_client.post(
        "/auth/login",
        json={"email": _TEST_USER["email"], "password": _TEST_USER["password"]},
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(auth_token):
    """Return Authorization header dict for test requests."""
    return {"Authorization": f"Bearer {auth_token}"}


# ---------------------------------------------------------------------------
# Sample task fixture (8 diverse tasks)
# ---------------------------------------------------------------------------

_SAMPLE_TASK_PAYLOADS = [
    {"title": "Finish project report",  "category": "Work",      "priority": "High",     "source": "manual"},
    {"title": "Buy groceries",          "category": "Personal",  "priority": "Medium",   "source": "manual"},
    {"title": "Doctor checkup",         "category": "Health",    "priority": "Critical", "source": "voice"},
    {"title": "Pay rent",               "category": "Finance",   "priority": "High",     "source": "manual"},
    {"title": "Study for exam",         "category": "Education", "priority": "High",     "source": "manual"},
    {"title": "Call mom",               "category": "Personal",  "priority": "Low",      "source": "manual"},
    {"title": "Gym session",            "category": "Health",    "priority": "Low",      "source": "voice"},
    {"title": "Submit tax return",      "category": "Finance",   "priority": "Critical", "source": "manual"},
]


@pytest.fixture(scope="session")
def sample_tasks(test_client, auth_headers):
    """Create 8 diverse tasks and return their response dicts."""
    tasks = []
    for payload in _SAMPLE_TASK_PAYLOADS:
        r = test_client.post("/tasks", json=payload, headers=auth_headers)
        assert r.status_code == 201, f"Sample task creation failed: {r.text}"
        tasks.append(r.json())
    return tasks
