# PLAN.md — Thought2Do Master Build Plan

> **For Claude Code:** Read this ENTIRE file before starting any work. This is the single source of truth for the project architecture, data models, APIs, and build order. Before executing any phase, re-read the relevant section AND the Architecture Reference to ensure consistency. After completing each phase, verify the checkpoint before moving on.
>
> **User's workflow:** "Read PLAN.md. Execute Phase N."

---

## Project Overview

**Thought2Do** is an agentic, voice-driven task management system. A user speaks naturally, and a multi-agent LangGraph pipeline processes the utterance through Intent Classification → Task Decomposition → Deduplication → Prioritization, then persists structured tasks in MongoDB. The frontend is Streamlit; the backend is FastAPI. Voice-to-text uses OpenAI Whisper. Reasoning uses GPT-4o-mini.

### Core Value Proposition
The friction of logging a task is higher than the friction of doing the task. Thought2Do eliminates that friction — you speak naturally, and the system handles intent classification, task decomposition, deduplication, and priority assignment automatically.

---

## Architecture Reference

**This section is the canonical reference. All code must conform to these definitions exactly.**

### System Flow

```
[Browser Mic / Text Input]
       │
       ▼
[Streamlit Frontend :8501]
       │ HTTP (Bearer JWT)
       ▼
[FastAPI Backend :8000]
       │
       ├── /voice/transcribe ──► OpenAI Whisper STT ──► raw transcript
       ├── /voice/process    ──► transcript ──► LangGraph Pipeline ──► DB operations
       ├── /tasks/*           ──► Direct CRUD on MongoDB
       └── /auth/*            ──► Register / Login / JWT
       │
       ▼
[LangGraph Multi-Agent Pipeline]
       │
       ├── 1. Intent Agent ──► Classifies: CREATE / UPDATE / DELETE / QUERY / MIXED
       ├── 2. Decomposition Agent ──► Extracts structured tasks, resolves dates
       ├── 3. Deduplication Agent ──► Compares against existing tasks in MongoDB
       ├── 4. Prioritization Agent ──► Assigns/validates priority based on context
       └── 5. Execution Node ──► Performs DB operations (create/update/delete/query)
       │
       ▼
[MongoDB Atlas] ──► User-isolated task storage
       │
       ▼ (optional)
[Pinecone] ──► Semantic search for dedup + future vault feature
```

### Project Structure

```
thought2do/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI entry, CORS, router includes
│   │   ├── config.py                   # pydantic-settings, env loading
│   │   ├── dependencies.py             # DB connection, auth dependency, vector service
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── task.py                 # Task Pydantic schemas
│   │   │   └── user.py                 # User Pydantic schemas
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                 # POST /auth/register, /auth/login, GET /auth/me
│   │   │   ├── tasks.py                # CRUD /tasks endpoints
│   │   │   └── voice.py                # POST /voice/transcribe, /voice/process
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py         # Password hashing, JWT encode/decode
│   │   │   ├── task_service.py         # MongoDB CRUD operations
│   │   │   ├── voice_service.py        # Whisper API transcription
│   │   │   └── vector_service.py       # Pinecone (optional, guarded by is_enabled())
│   │   ├── agents/
│   │   │   ├── __init__.py             # parse_llm_json() utility
│   │   │   ├── state.py                # AgentState TypedDict
│   │   │   ├── graph.py                # LangGraph StateGraph + process_voice_input()
│   │   │   ├── intent_agent.py         # intent_node()
│   │   │   ├── decomposition_agent.py  # decomposition_node()
│   │   │   ├── dedup_agent.py          # dedup_node()
│   │   │   └── prioritization_agent.py # prioritization_node()
│   │   └── prompts/
│   │       ├── __init__.py
│   │       ├── intent_prompt.py        # INTENT_SYSTEM_PROMPT string
│   │       ├── decomposition_prompt.py # DECOMPOSITION_SYSTEM_PROMPT string
│   │       ├── dedup_prompt.py         # DEDUP_SYSTEM_PROMPT string
│   │       └── prioritization_prompt.py # PRIORITIZATION_SYSTEM_PROMPT string
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py                 # Fixtures: test_db, test_client, auth_token
│   │   ├── test_agents.py
│   │   ├── test_voice.py
│   │   ├── test_tasks.py
│   │   └── evaluation.py              # Standalone eval harness (not pytest)
│   └── requirements.txt
├── frontend/
│   ├── app.py                          # Streamlit main: auth gate, theme, layout
│   ├── pages/
│   │   ├── 1_Dashboard.py
│   │   ├── 2_Voice_Input.py
│   │   └── 3_Settings.py
│   ├── components/
│   │   ├── __init__.py
│   │   ├── task_card.py
│   │   ├── voice_recorder.py
│   │   ├── sidebar.py
│   │   └── auth_forms.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── api_client.py
│   │   └── theme.py
│   ├── static/
│   │   └── style.css
│   └── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── Makefile
├── docker-compose.yml
└── PLAN.md                             # THIS FILE
```

### Canonical Data Models

**These are the exact field names and types. Every file in the project must use these.**

#### MongoDB: `users` collection
```json
{
  "_id": "ObjectId",
  "email": "string (unique)",
  "name": "string",
  "hashed_password": "string",
  "created_at": "datetime (UTC)"
}
```

#### MongoDB: `tasks` collection
```json
{
  "_id": "ObjectId",
  "user_id": "string (references users._id)",
  "title": "string",
  "description": "string | null",
  "category": "string enum: Work | Personal | Health | Finance | Education | General",
  "priority": "string enum: Critical | High | Medium | Low",
  "deadline": "datetime | null",
  "status": "string enum: pending | in_progress | completed | cancelled",
  "tags": ["string"],
  "parent_task_id": "string | null (for subtasks from decomposition)",
  "source": "string enum: voice | manual | decomposed",
  "created_at": "datetime (UTC)",
  "updated_at": "datetime (UTC)"
}
```

#### Pydantic Schemas (backend/app/models/task.py)
```
TaskCreate:      title, description?, category="General", priority="Medium", deadline?, tags=[], parent_task_id?, source="voice"
TaskUpdate:      title?, description?, category?, priority?, deadline?, status?, tags?
TaskResponse:    id, title, description?, category, priority, deadline?, status, tags, parent_task_id?, source, user_id, created_at, updated_at
TaskListResponse: tasks: List[TaskResponse], total: int
```

#### Pydantic Schemas (backend/app/models/user.py)
```
UserRegister:   email (EmailStr), password (str, min 8), name (str)
UserLogin:      email (EmailStr), password (str)
UserResponse:   id, email, name, created_at
```

### AgentState (backend/app/agents/state.py)
```python
class AgentState(TypedDict):
    transcript: str                     # Raw voice transcript
    user_id: str                        # Current user's ID
    existing_tasks: List[dict]          # User's current tasks (context for agents)
    intent: Optional[str]               # CREATE | UPDATE | DELETE | QUERY | MIXED
    extracted_tasks: List[dict]         # Tasks parsed by decomposition agent
    dedup_results: List[dict]           # Tasks after dedup filtering
    final_tasks: List[dict]             # Tasks after prioritization
    actions_taken: List[dict]           # Log of DB operations performed
    reasoning_log: List[str]            # Chain-of-thought from each agent
    current_datetime: str               # ISO timestamp for relative date resolution
    error: Optional[str]                # Error message if pipeline fails
```

### API Endpoints

| Method | Path | Auth | Request Body | Response |
|--------|------|------|-------------|----------|
| POST | /auth/register | No | UserRegister | UserResponse (201) |
| POST | /auth/login | No | UserLogin | {access_token, token_type, user: UserResponse} |
| GET | /auth/me | Yes | — | UserResponse |
| GET | /tasks | Yes | Query: status?, category?, priority?, skip?, limit? | TaskListResponse |
| POST | /tasks | Yes | TaskCreate | TaskResponse (201) |
| GET | /tasks/{id} | Yes | — | TaskResponse |
| PUT | /tasks/{id} | Yes | TaskUpdate | TaskResponse |
| DELETE | /tasks/{id} | Yes | — | 204 |
| POST | /voice/transcribe | Yes | File (audio) | {transcript, language, duration} |
| POST | /voice/process | Yes | File (audio) OR {transcript: str} | VoiceProcessResponse |

#### VoiceProcessResponse
```json
{
  "transcript": "string",
  "tasks_created": ["TaskResponse"],
  "tasks_updated": ["TaskResponse"],
  "tasks_deleted": ["string (task IDs)"],
  "tasks_queried": ["TaskResponse"],
  "agent_reasoning": "string (joined reasoning_log)"
}
```

### LLM Agent Output Contracts

**Intent Agent output:**
```json
{"intent": "CREATE|UPDATE|DELETE|QUERY|MIXED", "confidence": 0.0-1.0, "reasoning": "string", "sub_intents": [{"intent": "...", "segment": "..."}]}
```

**Decomposition Agent output:**
```json
{"tasks": [{"title": "str", "description": "str|null", "category": "str", "priority": "str", "deadline": "ISO datetime|null", "tags": ["str"], "action": "create|update|delete|query", "update_target_id": "str|null", "update_fields": {}}], "reasoning": "str"}
```

**Dedup Agent output:**
```json
{"results": [{"task": {}, "status": "unique|duplicate|related", "matched_existing_id": "str|null", "recommendation": "create|skip|merge|update|delete", "merge_fields": {}, "reasoning": "str"}]}
```

**Prioritization Agent output:**
```json
{"tasks": [{"task": {}, "priority_changed": true, "original_priority": "str", "new_priority": "str", "reasoning": "str"}], "reprioritize_existing": [{"task_id": "str", "current_priority": "str", "suggested_priority": "str", "reasoning": "str"}], "overall_reasoning": "str"}
```

### Environment Variables (.env)
```
OPENAI_API_KEY=sk-...
MONGODB_URI=mongodb+srv://...
MONGODB_DB_NAME=thought2do
JWT_SECRET_KEY=<random-64-char-string>
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=1440
PINECONE_API_KEY=<optional>
PINECONE_INDEX_NAME=thought2do-vault
```

### Tech Stack (exact versions for requirements.txt)

**Backend:**
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0
pydantic-settings>=2.0
motor>=3.3.0
pymongo>=4.6.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.9
openai>=1.30.0
langchain>=0.3.0
langchain-openai>=0.2.0
langgraph>=0.2.0
pinecone-client>=3.0.0
httpx>=0.27.0
```

**Frontend:**
```
streamlit>=1.38.0
requests>=2.31.0
streamlit-webrtc>=0.47.0
extra-streamlit-components>=0.1.60
pydub>=0.25.1
```

### UI Design Spec

- **Primary theme:** Dark mode (with light mode toggle)
- **Colors (dark):** bg=#0E1117, secondary_bg=#1A1D23, card_bg=#1E2128, text=#FAFAFA, accent=#6C63FF (purple), success=#00D68F, warning=#FFB547, danger=#FF6B6B, muted=#8B949E
- **Colors (light):** bg=#FFFFFF, secondary_bg=#F6F8FA, card_bg=#FFFFFF, text=#24292F, same accent/success/warning/danger
- **Priority card borders:** Critical=#FF6B6B, High=#FFB547, Medium=#6C63FF, Low=#8B949E
- **Priority icons:** 🔴 Critical, 🟠 High, 🔵 Medium, ⚪ Low
- **Source icons:** 🎙️ voice, ✏️ manual, 🔀 decomposed
- **Landing tagline:** "Think it. Say it. Done."
- **App icon:** 🧠

---

## Build Phases

---

### Phase 1: Project Scaffolding & Environment Setup

**Goal:** Create the entire folder structure, all empty/stub files, and configuration files.

Create the professional monorepo project called "thought2do" matching the Project Structure in the Architecture Reference above. Specifics:

- Every `.py` file should have a module-level docstring describing its purpose. No application logic yet — just the skeleton.
- All `__init__.py` files should be empty (or have the module docstring only).
- `backend/requirements.txt` and `frontend/requirements.txt` with the exact dependencies from the Tech Stack section above.

**`.env.example`** — template with all keys from the Environment Variables section, using placeholder values.

**`.gitignore`:**
```
__pycache__/
*.pyc
.env
.venv/
venv/
node_modules/
.streamlit/
*.egg-info/
dist/
build/
.pytest_cache/
```

**`Makefile`:**
```makefile
install-backend:
	cd backend && pip install -r requirements.txt

install-frontend:
	cd frontend && pip install -r requirements.txt

install: install-backend install-frontend

run-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

run-frontend:
	cd frontend && streamlit run app.py --server.port 8501

test:
	cd backend && python -m pytest tests/ -v

evaluate:
	cd backend && python -m tests.evaluation

docker-build:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down
```

**`README.md`:** Professional README with project title, one-paragraph description, the System Flow diagram (copy from Architecture Reference), setup instructions (clone → create .env → make install → make run-backend → make run-frontend in separate terminals), tech stack list, and a "Project Status: Under Development" note.

✅ **Checkpoint:** `ls -R thought2do/` shows the complete structure. `cat` any `.py` file shows a docstring. `cat .env.example` shows all keys. `cat Makefile` shows all targets.

---

### Phase 2: Configuration & Database Connection

**Goal:** Config loading, MongoDB connection, FastAPI app skeleton.

**Prereqs the user must complete before this phase:**
- MongoDB Atlas cluster created with URI ready
- `.env` file created from `.env.example` with real values filled in
- `make install-backend` run successfully
- Python 3.10+ confirmed

**`backend/app/config.py`:**
- Use `pydantic_settings.BaseSettings` to load from `.env`
- Fields matching the Environment Variables section exactly
- `PINECONE_API_KEY` and `PINECONE_INDEX_NAME` should be `Optional[str] = None`
- Create a cached settings instance using `@lru_cache` on a `get_settings()` function
- `model_config` with `env_file=".env"`

**`backend/app/dependencies.py`:**
- Async MongoDB client using `motor.motor_asyncio.AsyncIOMotorClient`, initialized once at module level
- `get_database()` dependency returning the database instance (db name from settings)
- `get_current_user()` dependency that:
  - Reads `Authorization` header (Bearer token)
  - Decodes JWT using `python-jose` (settings for secret key and algorithm)
  - Looks up user in MongoDB `users` collection by the `sub` claim (user_id)
  - Raises `HTTPException(401)` if token is invalid/expired or user not found
  - Returns the user document as a dict
- All async, proper type hints throughout

**`backend/app/main.py`:**
- `FastAPI(title="Thought2Do API", version="1.0.0")`
- CORS middleware: allow origins `["http://localhost:8501"]`, allow credentials, allow all methods and headers
- Router includes for auth, tasks, voice — use placeholder imports with `try/except ImportError` so the app starts even if routers aren't implemented yet
- Root `GET /` endpoint: returns `{"status": "ok", "message": "Thought2Do API is running"}`
- `@app.on_event("startup")` that pings MongoDB (`await db.command("ping")`) and prints/logs confirmation

✅ **Checkpoint:** `make run-backend` starts without errors. `curl http://localhost:8000/` returns `{"status":"ok","message":"Thought2Do API is running"}`. Console shows "Connected to MongoDB" (or similar).

---

### Phase 3: Authentication System

**Goal:** Full register/login/JWT auth flow.

**`backend/app/models/user.py`:**
- Pydantic schemas exactly matching the Canonical Data Models section:
  - `UserRegister`: email (EmailStr), password (str, min_length=8), name (str)
  - `UserLogin`: email (EmailStr), password (str)
  - `UserResponse`: id (str), email (str), name (str), created_at (datetime)
  - `UserInDB`: inherits UserResponse + hashed_password (str)

**`backend/app/services/auth_service.py`:**
- `hash_password(password: str) -> str` — passlib bcrypt
- `verify_password(plain: str, hashed: str) -> bool`
- `create_access_token(user_id: str, email: str) -> str` — JWT with `sub` = user_id, `email` = email, `exp` = now + settings.JWT_EXPIRATION_MINUTES
- `decode_access_token(token: str) -> dict` — returns payload or raises ValueError

**`backend/app/routers/auth.py`:**
- `POST /auth/register` — check duplicate email (400), hash password, insert into `users` collection, return UserResponse (201)
- `POST /auth/login` — find by email, verify password, return `{"access_token": str, "token_type": "bearer", "user": UserResponse}` (200). Bad credentials → 401
- `GET /auth/me` — protected via `get_current_user` dependency, returns UserResponse (200)

MongoDB `users` document schema matches the Canonical Data Models section. Convert `_id` ObjectId to string for `UserResponse.id`.

✅ **Checkpoint:**
```bash
# Register
curl -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" -d '{"email":"test@test.com","password":"testpass123","name":"Test User"}'
# → 201, UserResponse

# Login
curl -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"test@test.com","password":"testpass123"}'
# → 200, {access_token, token_type, user}

# Me (use token from login response)
curl http://localhost:8000/auth/me -H "Authorization: Bearer <token>"
# → 200, UserResponse

# Me without token
curl http://localhost:8000/auth/me
# → 401
```

---

### Phase 4: Task CRUD

**Goal:** Full task create/read/update/delete with filtering and sorting.

**`backend/app/models/task.py`:**
- All Pydantic schemas exactly per the Canonical Data Models section
- Use `Literal` types for enum fields (category, priority, status, source) for validation
- `TaskResponse.id` is a string (converted from ObjectId)

**`backend/app/services/task_service.py`:**
Implement `TaskService` class:
- `__init__(self, db)` — takes the motor database instance
- `async create_task(task: TaskCreate, user_id: str) -> TaskResponse` — insert into `tasks` collection, auto-set `status="pending"`, `created_at`, `updated_at`
- `async get_tasks(user_id: str, status=None, category=None, priority=None, skip=0, limit=50) -> TaskListResponse` — filter by user_id always + optional filters. Sort: priority order (Critical=0, High=1, Medium=2, Low=3) then deadline ascending (nulls last)
- `async get_task(task_id: str, user_id: str) -> TaskResponse` — single task, 404 if not found or wrong user
- `async update_task(task_id: str, user_id: str, updates: TaskUpdate) -> TaskResponse` — partial update, auto-set `updated_at`, 404 if not found
- `async delete_task(task_id: str, user_id: str) -> bool` — delete, 404 if not found
- `async get_tasks_for_context(user_id: str, limit: int = 20) -> List[dict]` — returns simplified task dicts (id, title, category, priority, deadline, status, tags) for active tasks only (not completed/cancelled), sorted by priority. This is used for injecting into LLM prompts.

**`backend/app/routers/tasks.py`:**
- All endpoints per the API Endpoints table
- All require `get_current_user` dependency
- Create `TaskService` instance using the database dependency
- Proper status codes: 201 for create, 200 for get/update, 204 for delete, 404 for not found

✅ **Checkpoint:**
```bash
TOKEN="<from login>"
# Create
curl -X POST http://localhost:8000/tasks -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"Buy groceries","category":"Personal","priority":"Low"}'
# → 201

# List
curl http://localhost:8000/tasks -H "Authorization: Bearer $TOKEN"
# → {tasks: [...], total: 1}

# List with filter
curl "http://localhost:8000/tasks?category=Personal" -H "Authorization: Bearer $TOKEN"

# Update
curl -X PUT http://localhost:8000/tasks/<id> -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"status":"completed"}'

# Delete
curl -X DELETE http://localhost:8000/tasks/<id> -H "Authorization: Bearer $TOKEN"
# → 204
```

---

### Phase 5: Voice Service (Whisper STT)

**Goal:** Audio upload → Whisper transcription, plus the /voice/process endpoint (stubbed pipeline).

**`backend/app/services/voice_service.py`:**
Create `VoiceService` class:
- `__init__(self)` — initialize OpenAI client from settings
- `async transcribe(audio_file: UploadFile) -> dict`:
  - Accept audio formats: webm, wav, mp3, m4a, ogg, mpeg
  - Save to temp file using `tempfile.NamedTemporaryFile`
  - Call `openai.audio.transcriptions.create(model="whisper-1", file=audio_file)`
  - Clean up temp file in `finally` block
  - Return `{"transcript": str, "language": str, "duration": float}`
  - Handle errors: file too large (>25MB), invalid format, API errors → raise HTTPException with clear message

**`backend/app/routers/voice.py`:**
- `POST /voice/transcribe` — accepts multipart file upload, requires auth, validates audio MIME type, returns transcript
- `POST /voice/process` — accepts EITHER:
  - Multipart file upload (audio) → transcribes first, then processes
  - JSON body `{"transcript": "string"}` → skips transcription
  - Requires auth
  - **For now:** stub the agent pipeline call. Return the transcript with empty task lists matching `VoiceProcessResponse` from Architecture Reference. Add a `# TODO: Wire in process_voice_input() from agents.graph` comment where the pipeline call will go.

✅ **Checkpoint:**
```bash
# Transcribe audio
curl -X POST http://localhost:8000/voice/transcribe -H "Authorization: Bearer $TOKEN" -F "file=@test_audio.webm"
# → {transcript, language, duration}

# Process text (stub)
curl -X POST http://localhost:8000/voice/process -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"transcript":"remind me to buy milk"}'
# → {transcript: "remind me to buy milk", tasks_created: [], tasks_updated: [], tasks_deleted: [], tasks_queried: [], agent_reasoning: ""}
```

---

### Phase 6: Agent Prompt Templates

**Goal:** Write the four detailed system prompts that drive the intelligence of the pipeline.

Each prompt is a Python string constant in its respective file under `backend/app/prompts/`. Each prompt must produce JSON output matching the LLM Agent Output Contracts in the Architecture Reference EXACTLY. Use `{current_datetime}` and `{existing_tasks}` as template placeholders that will be `.format()`-ed at runtime.

**`backend/app/prompts/intent_prompt.py` — `INTENT_SYSTEM_PROMPT`:**
- Role: Intent Classification Agent for a voice-driven task management system
- Input: A voice transcript and the user's existing task list
- Job: Classify PRIMARY intent as exactly one of: CREATE, UPDATE, DELETE, QUERY, MIXED
  - CREATE: adding new tasks ("remind me to...", "I need to...", "add...", "don't forget to...")
  - UPDATE: modifying existing tasks ("push X to...", "change priority of...", "mark X as done", "I already did X")
  - DELETE: removing tasks ("forget about...", "cancel...", "remove...", "never mind about...", "actually scratch that")
  - QUERY: asking about tasks ("what do I have...", "what's due...", "show me...", "am I free on...")
  - MIXED: transcript contains multiple distinct intents ("add groceries and also mark my report as done")
- Edge cases:
  - "Actually, forget that last one" = DELETE (refers to most recent task)
  - "I already did X" = UPDATE (mark as completed, not DELETE)
  - "Can you remind me about X?" = QUERY if X exists, CREATE if it doesn't
  - Ambiguous → default to CREATE
- Output: JSON matching Intent Agent contract from Architecture Reference
- Include `{existing_tasks}` placeholder for context injection

**`backend/app/prompts/decomposition_prompt.py` — `DECOMPOSITION_SYSTEM_PROMPT`:**
- Role: Task Decomposition Agent — extracts structured tasks from natural speech
- Input: transcript, classified intent, existing tasks, current datetime
- Job:
  - Parse into one or more structured task objects
  - Handle compound utterances ("do X and also Y" = two separate tasks)
  - Resolve relative dates against `{current_datetime}`: "tomorrow", "this Friday", "next week" = Monday, "end of month", "in 3 days", "by end of day"
  - Infer category from context keywords: work/project/meeting/report → "Work", grocery/shopping/cook → "Personal", doctor/gym/workout/health → "Health", bills/payment/budget → "Finance", homework/study/class/exam → "Education", anything else → "General"
  - Infer priority from urgency words: "urgent"/"ASAP"/"critical"/"emergency" → "Critical", "important"/"soon"/"high priority" → "High", no urgency cue → "Medium", "whenever"/"low priority"/"sometime"/"no rush" → "Low"
  - For UPDATE intent: identify which existing task is being modified (match by title/description similarity) and what fields are changing
  - For DELETE intent: identify which existing task(s) to remove
  - For QUERY intent: extract query parameters (date range, category, status filters)
- Edge cases:
  - Vague tasks like "handle it" or "take care of that" — keep title as-is, add tag `["needs_clarification"]`
  - Compound utterances — extract up to 10 tasks max
  - Time-of-day mentions ("at 3pm", "by end of day") — parse into deadline datetime
  - No deadline mentioned → deadline = null (don't invent one)
- Output: JSON matching Decomposition Agent contract from Architecture Reference

**`backend/app/prompts/dedup_prompt.py` — `DEDUP_SYSTEM_PROMPT`:**
- Role: Deduplication Agent — prevents duplicate tasks
- Input: newly extracted tasks AND user's existing task list
- Job:
  - Compare each new task against ALL existing tasks
  - DUPLICATE: same essential action + same subject, even if worded differently ("call doctor" = "phone the doctor" = "ring up my physician")
  - RELATED: overlapping subject but different action ("buy groceries" existing + "make grocery list" new)
  - UNIQUE: no meaningful overlap
  - For duplicates: recommend SKIP (don't create) or MERGE (update existing with new info like a changed deadline)
  - For updates/deletes: match transcript reference to most likely existing task
- Edge cases:
  - Same task but existing one is COMPLETED → new one is UNIQUE (it's a new instance)
  - Partial word match doesn't mean duplicate: "Buy milk" vs "Buy a car" → UNIQUE
  - "Remind me to call the doctor" when "Call doctor" is pending → DUPLICATE, recommend SKIP
  - "Call the doctor on Tuesday" when "Call doctor" exists with no deadline → MERGE (add deadline)
- Output: JSON matching Dedup Agent contract from Architecture Reference

**`backend/app/prompts/prioritization_prompt.py` — `PRIORITIZATION_SYSTEM_PROMPT`:**
- Role: Prioritization Agent — ensures priorities reflect reality
- Input: final set of tasks to create/update, plus full existing task list, current datetime
- Job:
  - Assign/validate priority for new tasks considering overall workload
  - Deadline proximity: Medium task due tomorrow → should be High. Low task due today → should be High or Critical.
  - Workload balance: if user has 10 Critical tasks, that's suspicious — flag it, don't just add another Critical
  - New Critical task added → check if existing Critical tasks should be re-evaluated
  - For re-ranking: suggest priority changes to EXISTING tasks if warranted (e.g., deadline passed → lower priority or flag as overdue)
- Do NOT change titles, descriptions, categories, or deadlines — only priority
- Output: JSON matching Prioritization Agent contract from Architecture Reference

✅ **Checkpoint:** Read each prompt file. Verify the JSON output schema in the prompt instructions matches the corresponding contract in the Architecture Reference. Verify `{current_datetime}` and `{existing_tasks}` placeholders are present where needed.

---

### Phase 7: Agent Node Implementations

**Goal:** Four async functions that call GPT-4o-mini and update AgentState.

**`backend/app/agents/__init__.py` — shared utility:**
```python
def parse_llm_json(response_text: str) -> dict:
    """Strip markdown code fences and parse JSON. Raises ValueError with context on failure."""
```
- Strip ```json and ``` fences
- `json.loads()` the cleaned text
- On failure: raise `ValueError(f"Failed to parse LLM response: {response_text[:200]}")` with the first 200 chars for debugging

**`backend/app/agents/state.py`:**
- Implement the `AgentState` TypedDict exactly as defined in the Architecture Reference

**Each agent node** (`intent_agent.py`, `decomposition_agent.py`, `dedup_agent.py`, `prioritization_agent.py`):
- Async function signature: `async def <name>_node(state: AgentState) -> dict`
- Import its prompt from `prompts/`
- Build the full prompt by `.format()`-ing the template with state variables (existing_tasks as JSON string, current_datetime, etc.)
- Call `ChatOpenAI(model="gpt-4o-mini", temperature=0)` via `ainvoke()` with system message + human message
- Parse response using `parse_llm_json()`
- On JSON parse failure: retry ONCE with the same input. If still fails, set `state["error"]` and return
- Update the relevant AgentState fields (each node only sets its own fields)
- Append reasoning string to `state["reasoning_log"]`
- Use Python `logging` module for debug output (log raw LLM response before parsing)
- 30-second timeout per LLM call (use `asyncio.wait_for` or model kwargs)

Return value is a partial dict — only the keys that this node updates. LangGraph merges it into the full state.

✅ **Checkpoint:** For each agent, write a quick test:
```python
import asyncio
from app.agents.intent_agent import intent_node
state = {"transcript": "remind me to buy milk", "existing_tasks": [], "reasoning_log": [], "current_datetime": "2026-04-23T10:00:00"}
result = asyncio.run(intent_node(state))
print(result)  # Should have "intent": "CREATE"
```

---

### Phase 8: LangGraph Pipeline + Wire to API

**Goal:** Wire the four agents into a LangGraph StateGraph, add the execution node, connect to the voice endpoint.

**`backend/app/agents/graph.py`:**

1. Import `StateGraph`, `END` from `langgraph.graph`
2. Import all four agent node functions and AgentState
3. Import TaskService

**Graph definition:**
- Nodes: `"intent"`, `"decomposition"`, `"dedup"`, `"prioritization"`, `"execute"`
- Routing after intent node:
  - If `state["intent"] == "QUERY"` → go to `"execute"` (skip decomposition/dedup/prioritization)
  - Otherwise → go to `"decomposition"`
- Linear edges: `decomposition → dedup → prioritization → execute → END`
- Start edge: `START → intent`

**Execute node** (`async def execute_node(state: AgentState, db) -> dict`):
- Use `functools.partial` or closure to inject the db dependency
- Create `TaskService(db)` instance
- Based on intent:
  - **CREATE:** For each task in `final_tasks`, call `task_service.create_task()`. Collect created TaskResponse objects.
  - **UPDATE:** For each task with `action="update"`, find `update_target_id`, call `task_service.update_task()`. Collect updated TaskResponse objects.
  - **DELETE:** For each task with `action="delete"`, call `task_service.delete_task()`. Collect deleted task IDs.
  - **QUERY:** Call `task_service.get_tasks()` with extracted filters. Collect results.
  - **MIXED:** Handle each sub-action appropriately (some creates, some updates, some deletes).
- Log all operations to `state["actions_taken"]` as `{"action": "created|updated|deleted", "task_id": "...", "title": "..."}`
- Handle errors per-task with try/except — one failed operation doesn't stop the others

**Main entry function:**
```python
async def process_voice_input(transcript: str, user_id: str, db) -> dict:
```
- Fetch existing tasks via `TaskService(db).get_tasks_for_context(user_id)`
- Build initial AgentState with all fields
- Compile the graph: `graph = workflow.compile()`
- Invoke: `result = await graph.ainvoke(initial_state)`
- Transform result into `VoiceProcessResponse` shape from Architecture Reference
- Return it

**Update `backend/app/routers/voice.py`:**
- Replace the stub in `POST /voice/process` with a call to `process_voice_input()`
- Pass transcript, `current_user["_id"]` (as string), and database from dependency
- Return response matching `VoiceProcessResponse`

✅ **Checkpoint:**
```bash
# Full pipeline test
curl -X POST http://localhost:8000/voice/process \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"transcript": "Remind me to submit my project proposal by Thursday, it is pretty urgent, and also I need to buy groceries sometime this week"}'
# → Should return 2 tasks_created:
#   1. "Submit project proposal" - Work/Education - High/Critical - Thursday deadline
#   2. "Buy groceries" - Personal - Low/Medium - this week

# Verify in DB
curl http://localhost:8000/tasks -H "Authorization: Bearer $TOKEN"
# → Both tasks visible
```

---

### Phase 9: Frontend Foundation (Theme, Auth, API Client)

**Goal:** Streamlit app shell with auth gate, theme system, API client.

**`frontend/utils/theme.py`:**
- `DARK_THEME` and `LIGHT_THEME` dicts with ALL colors from UI Design Spec
- `get_theme()` reads `st.session_state.get("theme", "dark")`, returns the right dict
- `get_custom_css(theme: dict) -> str` returns comprehensive CSS that styles:
  - Page background, text color
  - Streamlit default elements (buttons, inputs, selectboxes, text areas) to match theme
  - Custom classes: `.task-card`, `.task-card-critical`, `.task-card-high`, `.task-card-medium`, `.task-card-low` with left-border colors
  - Priority badge styles (`.badge-critical`=red, `.badge-high`=orange, `.badge-medium`=blue, `.badge-low`=gray)
  - Category pill styles (small rounded labels)
  - Hover effects (shadow transitions)
  - Scrollbar styling for dark mode
  - Pulsing glow animation for active recording button

**`frontend/utils/api_client.py`:**
- `APIClient` class with `base_url="http://localhost:8000"` default
- Token management: `set_token()`, `get_headers()` returning `{"Authorization": f"Bearer {token}"}`
- Methods matching ALL API endpoints from Architecture Reference:
  - `register(email, password, name)`, `login(email, password)`, `get_me()`
  - `get_tasks(status, category, priority)`, `create_task(data)`, `update_task(id, data)`, `delete_task(id)`
  - `transcribe_audio(audio_bytes, filename)`, `process_voice(audio_bytes=None, transcript=None)`
- All methods return response JSON on success, `{"error": "message"}` on failure
- `get_api_client()` function that stores singleton in `st.session_state`

**`frontend/components/auth_forms.py`:**
- `render_login_form()` — Streamlit form: email + password + submit. On success: store token + user in session_state, `st.rerun()`
- `render_register_form()` — Streamlit form: name + email + password + confirm password. Validate match. On success: auto-login + `st.rerun()`
- Error/success messages via `st.error()` / `st.success()`
- Center the forms with a max-width card look using CSS

**`frontend/app.py`:**
- `st.set_page_config(page_title="Thought2Do", page_icon="🧠", layout="wide", initial_sidebar_state="expanded")`
- Inject theme CSS via `st.markdown(get_custom_css(theme), unsafe_allow_html=True)`
- Auth gate: if no `st.session_state.token` → show landing page
- Landing page: app title "Thought2Do" in large styled text, tagline "Think it. Say it. Done.", brief description, login/register tabs using `st.tabs`
- Authenticated state: sidebar with user info, theme toggle, logout button
- Logout clears session_state and reruns

✅ **Checkpoint:** `make run-frontend` (with backend also running) → styled dark-mode landing page. Register → login → see authenticated layout with sidebar. Logout works. Theme toggle switches colors.

---

### Phase 10: Voice Input Page

**Goal:** Voice recording UI with processing pipeline visualization.

**`frontend/components/voice_recorder.py`:**
- Use `st.audio_input("Record your thought")` as the PRIMARY voice input method (built into recent Streamlit versions)
- Below it: `st.text_area("Or type your thought here", placeholder="e.g., Remind me to submit my report by Friday...")` as a text fallback
- If `st.audio_input` is not available (older Streamlit), fall back to `st.file_uploader` accepting audio formats

**`frontend/pages/2_Voice_Input.py`:**
Layout in two columns:
- **Left column (~60%):**
  - Header: "🎙️ Voice Input" with subtitle "Speak your mind, we'll handle the rest"
  - Voice recorder component
  - Text area fallback
  - Large "🚀 Process" button (`use_container_width=True`)
  - After processing: show raw transcript in an expander

- **Right column (~40%):**
  - "Processing Pipeline" header
  - Vertical progress indicator showing 4 agent stages: Intent → Decomposition → Dedup → Prioritization
  - Before processing: stages are grayed out
  - During processing: show spinner with "🤔 Thinking..."
  - After processing: stages light up (green checkmarks), show results
  - Result cards for each task created/updated/deleted — styled with priority border, category badge, action badge (✅ Created, ✏️ Updated, 🗑️ Deleted)
  - "Agent Reasoning" expander showing chain-of-thought from each agent

- **Bottom section: "Quick Actions"**
  - Clickable example phrases that auto-fill the text area:
    - "Remind me to submit my project by Friday, it's urgent"
    - "I need to buy groceries and also call the dentist"
    - "Mark my gym task as done"
    - "What's on my plate this week?"
  - Use `st.button` for each, on click → set session_state text → rerun

Processing flow: user records/types → clicks Process → spinner → API call to `/voice/process` → display results → `st.toast("✅ Tasks processed!")`

✅ **Checkpoint:** Navigate to Voice Input. Type a test phrase. Click Process. See tasks appear with correct metadata. Agent reasoning shows in expander. Quick action buttons work.

---

### Phase 11: Task Dashboard

**Goal:** The main task view with filtering, grouping, inline actions.

**`frontend/components/task_card.py`:**
`render_task_card(task: dict, on_complete_key: str, on_delete_key: str)` — renders a styled HTML card:
- Left color bar: priority colors from UI Design Spec
- Title (bold, larger). If completed → strikethrough
- Category pill badge
- Priority badge with icon (🔴🟠🔵⚪ from UI Design Spec)
- Deadline: relative text ("Due tomorrow", "Due in 3 days", "⚠️ Overdue!") with color coding (red if overdue, yellow if due today/tomorrow)
- Tags as small pills
- Source icon (🎙️✏️🔀 from UI Design Spec)
- Status badge (pending=blue, in_progress=yellow, completed=green, cancelled=gray)
- Subtle hover shadow via CSS

**`frontend/components/sidebar.py`:**
`render_sidebar()`:
- User name + email at top
- Filter section:
  - Status: All / Pending / In Progress / Completed (selectbox)
  - Category: All / Work / Personal / Health / Finance / Education / General (selectbox)
  - Priority: All / Critical / High / Medium / Low (selectbox)
  - Store selections in session_state
- Stats: total active, completed today, overdue count
- Theme toggle button (🌙 / ☀️)
- Logout button at bottom

**`frontend/pages/1_Dashboard.py`:**
- Call `render_sidebar()` in the sidebar
- Page header: "📋 My Tasks" with today's date
- Top metrics row (4 columns with `st.metric`): Total Active, Due Today, Overdue (red if >0), Completed This Week
- Fetch tasks from API with current filter values from session_state
- Sort options: selectbox with "Priority" (default), "Deadline", "Created Date"
- Task list grouped by priority with section headers ("🔴 Critical", "🟠 High", "🔵 Medium", "⚪ Low")
- Each task card has action buttons below it (use `st.columns` within a loop):
  - ✅ Complete → calls `update_task(id, {"status": "completed"})` → `st.toast` → rerun
  - ✏️ Edit → toggles an expander with editable fields (title, category, priority, deadline, status) → Save button → `update_task` → rerun
  - 🗑️ Delete → confirmation via `st.popover` or second click → `delete_task` → `st.toast` → rerun
- "➕ Add Task" button at top → expander/form with TaskCreate fields → `create_task` → rerun
- Empty state: "No tasks yet! Head to Voice Input to add your first task 🎙️" with a button that links to Voice Input page (`st.page_link`)

✅ **Checkpoint:** Dashboard shows tasks grouped by priority. Metrics are accurate. Complete/edit/delete work with toast feedback. Filters narrow results. Manual add works. Empty state shows when no tasks.

---

### Phase 12: Pinecone Vector Store (Optional)

**Goal:** Optional vector DB integration — the entire app works identically with or without it.

**CRITICAL RULE:** If `PINECONE_API_KEY` is not set in `.env`, nothing breaks. No errors, no warnings in the UI. Just a one-time `logger.info("Pinecone not configured, vector features disabled")` at startup.

**`backend/app/services/vector_service.py`:**
```python
class VectorService:
    def __init__(self, api_key: str = None, index_name: str = None):
        if not api_key:
            self.enabled = False
            return
        # Initialize Pinecone, connect to index
        self.enabled = True

    def is_enabled(self) -> bool:
        return self.enabled
```

Methods (all no-op silently when `not self.enabled`):
- `async upsert_task(task_id, user_id, task_data)` — embed `"{title}. {description}. Category: {category}"` using `text-embedding-3-small`, upsert to Pinecone with metadata, namespace=user_id
- `async search_similar(query, user_id, top_k=5) -> List[dict]` — embed query, search, return results with scores
- `async delete_task(task_id, user_id)` — delete vector
- `async upsert_link(link_id, user_id, url, title, description, tags)` — for future vault feature
- `async search_vault(query, user_id, top_k=3) -> List[dict]` — for future vault feature

**Integration points:**
- `dependencies.py`: add `get_vector_service()` dependency, cached, reads settings
- `task_service.py`: after `create_task`, call `vector_service.upsert_task()` if available. After `delete_task`, call `vector_service.delete_task()`. Vector service is optional — use try/except, never let vector failure break task operations.
- `dedup_agent.py`: if vector service is enabled, use `search_similar()` as supplemental signal alongside LLM-based dedup (add similar tasks to the dedup prompt context)

✅ **Checkpoint:**
- Without PINECONE_API_KEY: app works exactly as before, no errors
- With PINECONE_API_KEY: tasks are embedded on create, deleted on delete, dedup has extra context

---

### Phase 13: Settings Page & Final UI Polish

**Goal:** Settings page + polish pass across all frontend pages.

**`frontend/pages/3_Settings.py`:**
Sections:
1. **Profile:** user name, email (read-only), member since date
2. **Appearance:** dark/light mode toggle with live preview
3. **Task Defaults:** default category dropdown, default priority dropdown — saved in `st.session_state`, used as defaults in manual task creation
4. **Voice Settings:** info about which voice input method is active
5. **Data Management:**
   - "📥 Export Tasks" — `st.download_button` that exports all tasks as JSON
   - "🧹 Clear Completed" — deletes all completed tasks (with confirmation)
   - Statistics: total created, total completed, most common category, average tasks per day
6. **About:** app version "1.0.0", tech stack credits (OpenAI Whisper, GPT-4o-mini, LangGraph, MongoDB Atlas, FastAPI, Streamlit), GitHub link placeholder

**Polish pass — apply to ALL frontend files:**
1. Consistent `st.spinner("Loading...")` on every page load / API call
2. `st.toast()` on every successful action (create, update, delete, login, etc.)
3. `try/except` on ALL API calls — show `st.error("Something went wrong: ...")` on failure, never raw tracebacks
4. Every page/section has a friendly empty state (not just blank space)
5. Add `st.session_state` initialization at the top of `app.py` for all shared state keys
6. Connection status: in sidebar, show 🟢 or 🔴 based on a quick `/` health check to backend
7. All `st.button` calls use `use_container_width=True`
8. CSS transitions: card hovers, theme toggle smoothness

✅ **Checkpoint:** Settings page works fully. Export downloads JSON. Theme toggle is smooth. No page shows raw Python errors. Every action gives toast feedback. Connection indicator in sidebar.

---

### Phase 14: Tests & Evaluation Harness

**Goal:** Automated tests and a standalone evaluation script.

**`backend/tests/conftest.py`:**
- `test_db` fixture: use separate database `thought2do_test`, yield it, drop after tests
- `test_client` fixture: FastAPI `TestClient` using the app with test db
- `auth_token` fixture: register test user, login, return token string
- `sample_tasks` fixture: insert 5-10 diverse sample tasks (mix of categories, priorities, deadlines, statuses)

**`backend/tests/test_agents.py`:**
- `test_intent_classification`: 10 test cases:
  1. "remind me to buy milk" → CREATE
  2. "forget about the groceries" → DELETE
  3. "push my meeting to next week" → UPDATE
  4. "what's due tomorrow" → QUERY
  5. "add laundry and also mark my report as done" → MIXED
  6. "I already finished the presentation" → UPDATE
  7. "actually never mind about that" → DELETE
  8. "I need to study for my exam and buy groceries and call mom" → CREATE (compound)
  9. "what do I have on my plate this week" → QUERY
  10. "hmm let me think" → CREATE (ambiguous, defaults to CREATE)
- `test_decomposition`: 5 test cases (single task, multi-task, relative dates, priority keywords, vague task)
- `test_dedup`: 3 test cases (exact duplicate, semantic duplicate, non-duplicate)
- `test_full_pipeline`: 2 end-to-end (create + mixed scenario, verify DB state)

**`backend/tests/test_voice.py`:**
- Mock OpenAI Whisper, verify `/voice/transcribe` returns transcript
- Mock both Whisper and GPT-4o-mini, verify `/voice/process` returns correct structure

**`backend/tests/test_tasks.py`:**
- CRUD operations via test client
- User isolation: user A creates task, user B can't see it
- Filtering by status, category, priority
- Priority sort order: Critical first, then High, Medium, Low

**`backend/tests/evaluation.py`** (standalone script, NOT pytest):
- Define 20 labeled test utterances with ground truth: expected intent, number of tasks, categories, priorities, deadlines
- Run each through `process_voice_input()`
- Calculate and print:
  - Intent Classification Accuracy (%)
  - Task Count Accuracy (% with correct task count)
  - Category Accuracy (%)
  - Priority Accuracy (%)
  - Deadline Accuracy (%)
  - Dedup Precision (using 5 deliberate duplicate cases)
- Print formatted report to stdout
- Save results as JSON to `tests/eval_results.json`
- `--verbose` flag for per-utterance detail
- Run: `make evaluate` or `python -m tests.evaluation`

✅ **Checkpoint:** `make test` passes (or shows expected failures with notes). `make evaluate` prints a metrics report.

---

### Phase 15: Docker & Deployment

**Goal:** Containerize for production deployment.

**`backend/Dockerfile`:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`frontend/Dockerfile`:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
```

**`docker-compose.yml`** (root level):
```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env
    restart: unless-stopped
  frontend:
    build: ./frontend
    ports:
      - "8501:8501"
    environment:
      - BACKEND_URL=http://backend:8000
    depends_on:
      - backend
    restart: unless-stopped
```

**`.dockerignore`:**
```
__pycache__/
*.pyc
.env
.venv/
venv/
.git/
tests/
*.egg-info/
.pytest_cache/
```

**Update `frontend/utils/api_client.py`:** Read `BACKEND_URL` from environment variable with fallback to `http://localhost:8000` (for Docker networking where frontend talks to backend via service name).

**Update `README.md`:**
- Add "Docker Setup" section: `docker compose up --build` → app at localhost:8501
- Add "Deployment" section with brief GCP Cloud Run instructions (build images → push to GCR → deploy services)
- Add architecture diagram section (the System Flow from Architecture Reference)

✅ **Checkpoint:** `make docker-up` → both containers start. App accessible at `http://localhost:8501`. Login, create tasks, process voice — everything works through Docker.

---

## Working Instructions for Claude Code

1. **Always read this PLAN.md first.** Before writing any code, `cat PLAN.md` and understand the full architecture.
2. **Work one phase at a time.** Complete the checkpoint before starting the next phase.
3. **Use the Canonical Data Models exactly.** Field names, types, and enums must match across all files.
4. **Use the LLM Agent Output Contracts exactly.** The prompt templates must produce JSON matching these schemas, and the agent nodes must parse these schemas.
5. **The API Endpoints table is definitive.** Route paths, methods, auth requirements, and response shapes must match.
6. **Pinecone is optional everywhere.** Never let a missing PINECONE_API_KEY cause an error or warning.
7. **Test incrementally.** After each phase, verify the checkpoint manually or with the test suite.
8. **If something from a previous phase is broken, fix it before proceeding.** Don't paper over issues.
