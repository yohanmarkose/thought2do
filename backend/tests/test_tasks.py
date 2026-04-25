"""Tests for the task CRUD router.

Covers:
- Happy-path create / read / update / delete.
- User isolation: tasks created by user A are invisible to user B.
- Filtering by status, category, and priority.
- Priority sort order: Critical → High → Medium → Low.

All tests use the shared `test_client`, `auth_headers`, and
`sample_tasks` fixtures from conftest.py and hit a real (test) MongoDB.
No LLM mocking is required here.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECOND_USER = {
    "email": "other@example.com",
    "password": "OtherPass456!",
    "name": "Other User",
}


def _register_and_login(test_client, user: dict) -> dict:
    """Register (idempotent) + login; return auth headers."""
    test_client.post("/auth/register", json=user)
    r = test_client.post(
        "/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert r.status_code == 200, f"Login for {user['email']} failed: {r.text}"
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

def test_create_task_minimal(test_client, auth_headers):
    """POST /tasks with only required fields returns 201 with defaults."""
    r = test_client.post(
        "/tasks",
        json={"title": "Minimal task", "source": "manual"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Minimal task"
    assert data["status"] == "pending"
    assert data["priority"] == "Medium"
    assert data["category"] == "General"
    assert "id" in data
    assert "created_at" in data


def test_create_task_full(test_client, auth_headers):
    """POST /tasks with all optional fields persists them correctly."""
    payload = {
        "title": "Full task",
        "description": "A detailed task",
        "category": "Work",
        "priority": "High",
        "deadline": "2026-12-31T17:00:00+00:00",
        "tags": ["important", "q4"],
        "source": "manual",
    }
    r = test_client.post("/tasks", json=payload, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["description"] == "A detailed task"
    assert data["category"] == "Work"
    assert data["priority"] == "High"
    assert "important" in data["tags"]


def test_create_task_missing_title_returns_422(test_client, auth_headers):
    """POST /tasks without a title returns 422 (Pydantic validation)."""
    r = test_client.post("/tasks", json={"source": "manual"}, headers=auth_headers)
    assert r.status_code == 422


def test_create_task_requires_auth(test_client):
    """POST /tasks without a token returns 401."""
    r = test_client.post("/tasks", json={"title": "No auth", "source": "manual"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------

def test_list_tasks_returns_all_user_tasks(test_client, auth_headers, sample_tasks):
    """GET /tasks returns at least the seeded sample tasks."""
    r = test_client.get("/tasks", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= len(sample_tasks)
    assert isinstance(data["tasks"], list)
    assert len(data["tasks"]) >= len(sample_tasks)


def test_get_task_by_id(test_client, auth_headers, sample_tasks):
    """GET /tasks/{id} returns the exact task document."""
    task = sample_tasks[0]
    r = test_client.get(f"/tasks/{task['id']}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == task["id"]
    assert data["title"] == task["title"]


def test_get_nonexistent_task_returns_404(test_client, auth_headers):
    """GET /tasks/<bogus-id> returns 404."""
    r = test_client.get("/tasks/000000000000000000000000", headers=auth_headers)
    assert r.status_code == 404


def test_list_tasks_requires_auth(test_client):
    """GET /tasks without a token returns 401."""
    r = test_client.get("/tasks")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

def test_update_task_status(test_client, auth_headers):
    """PUT /tasks/{id} can mark a task as completed."""
    # Create a fresh task so the update doesn't affect sample_tasks
    create_r = test_client.post(
        "/tasks",
        json={"title": "Task to complete", "source": "manual"},
        headers=auth_headers,
    )
    task_id = create_r.json()["id"]

    r = test_client.put(
        f"/tasks/{task_id}",
        json={"status": "completed"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_update_task_priority(test_client, auth_headers):
    """PUT /tasks/{id} can change priority."""
    create_r = test_client.post(
        "/tasks",
        json={"title": "Priority update test", "source": "manual", "priority": "Low"},
        headers=auth_headers,
    )
    task_id = create_r.json()["id"]

    r = test_client.put(
        f"/tasks/{task_id}",
        json={"priority": "Critical"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["priority"] == "Critical"


def test_update_nonexistent_task_returns_404(test_client, auth_headers):
    """PUT /tasks/<bogus-id> returns 404."""
    r = test_client.put(
        "/tasks/000000000000000000000000",
        json={"status": "completed"},
        headers=auth_headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

def test_delete_task(test_client, auth_headers):
    """DELETE /tasks/{id} returns 204 and task is gone."""
    create_r = test_client.post(
        "/tasks",
        json={"title": "Task to delete", "source": "manual"},
        headers=auth_headers,
    )
    task_id = create_r.json()["id"]

    del_r = test_client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert del_r.status_code == 204

    get_r = test_client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert get_r.status_code == 404


def test_delete_nonexistent_task_returns_404(test_client, auth_headers):
    """DELETE /tasks/<bogus-id> returns 404."""
    r = test_client.delete("/tasks/000000000000000000000000", headers=auth_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------

def test_user_cannot_see_another_users_tasks(test_client, auth_headers, sample_tasks):
    """Tasks created by user A are not visible to user B."""
    other_headers = _register_and_login(test_client, _SECOND_USER)

    # User B should see 0 tasks (none created yet for this user)
    r = test_client.get("/tasks", headers=other_headers)
    assert r.status_code == 200
    # None of user A's task IDs should appear
    task_ids_a = {t["id"] for t in sample_tasks}
    task_ids_b = {t["id"] for t in r.json()["tasks"]}
    assert task_ids_a.isdisjoint(task_ids_b)


def test_user_cannot_read_another_users_task_by_id(test_client, auth_headers, sample_tasks):
    """GET /tasks/{id} with a different user's token returns 404."""
    other_headers = _register_and_login(test_client, _SECOND_USER)
    task_id = sample_tasks[0]["id"]
    r = test_client.get(f"/tasks/{task_id}", headers=other_headers)
    assert r.status_code == 404


def test_user_cannot_delete_another_users_task(test_client, auth_headers, sample_tasks):
    """DELETE /tasks/{id} with a different user's token returns 404."""
    other_headers = _register_and_login(test_client, _SECOND_USER)
    task_id = sample_tasks[0]["id"]
    r = test_client.delete(f"/tasks/{task_id}", headers=other_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def test_filter_by_status(test_client, auth_headers, sample_tasks):
    """GET /tasks?status=pending returns only pending tasks."""
    # Complete one task so the filter is meaningful
    test_client.put(
        f"/tasks/{sample_tasks[0]['id']}",
        json={"status": "completed"},
        headers=auth_headers,
    )
    r = test_client.get("/tasks?status=pending", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert all(t["status"] == "pending" for t in data["tasks"])


def test_filter_by_category(test_client, auth_headers, sample_tasks):
    """GET /tasks?category=Health returns only Health tasks."""
    r = test_client.get("/tasks?category=Health", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert all(t["category"] == "Health" for t in data["tasks"])
    assert len(data["tasks"]) >= 1


def test_filter_by_priority(test_client, auth_headers, sample_tasks):
    """GET /tasks?priority=Critical returns only Critical tasks."""
    r = test_client.get("/tasks?priority=Critical", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert all(t["priority"] == "Critical" for t in data["tasks"])
    assert len(data["tasks"]) >= 1


# ---------------------------------------------------------------------------
# Priority sort order
# ---------------------------------------------------------------------------

def test_priority_sort_order_critical_first(test_client, auth_headers, sample_tasks):
    """GET /tasks returns tasks ordered Critical → High → Medium → Low."""
    _PRIORITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    r = test_client.get("/tasks?limit=200", headers=auth_headers)
    assert r.status_code == 200
    tasks = r.json()["tasks"]
    ranks = [_PRIORITY_RANK[t["priority"]] for t in tasks if t["status"] == "pending"]
    assert ranks == sorted(ranks), (
        f"Tasks not in priority order. Got: {[t['priority'] for t in tasks if t['status'] == 'pending']}"
    )
