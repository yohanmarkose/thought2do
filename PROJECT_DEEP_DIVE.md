# Thought2Do — Project Deep Dive

> **Think it. Say it. Done.**  
> A voice-driven task management system powered by a multi-agent LangGraph pipeline.

---

## Table of Contents

1. [What Is This Project?](#1-what-is-this-project)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Tech Stack](#3-tech-stack)
4. [Directory Structure](#4-directory-structure)
5. [The Multi-Agent Pipeline](#5-the-multi-agent-pipeline)
   - [State Object](#51-state-object-the-shared-memory)
   - [Agent 1 — Intent Classifier](#52-agent-1--intent-classifier)
   - [Agent 2 — Task Decomposition](#53-agent-2--task-decomposition)
   - [Agent 3 — Deduplication](#54-agent-3--deduplication)
   - [Agent 4 — Prioritization](#55-agent-4--prioritization)
   - [Execution Node](#56-execution-node-deterministic-crud)
   - [LangGraph Wiring](#57-langgraph-wiring)
6. [Data Flow — End to End](#6-data-flow--end-to-end)
7. [Backend API Reference](#7-backend-api-reference)
8. [Database Schemas](#8-database-schemas)
9. [Frontend Pages](#9-frontend-pages)
10. [Services Layer](#10-services-layer)
11. [LLM Helper Utilities](#11-llm-helper-utilities)
12. [Authentication System](#12-authentication-system)
13. [Configuration & Environment](#13-configuration--environment)
14. [Key Architectural Decisions](#14-key-architectural-decisions)
15. [Worked Example — Full Pipeline Trace](#15-worked-example--full-pipeline-trace)

---

## 1. What Is This Project?

Thought2Do lets users **speak or type a thought** ("Schedule a dentist appointment for next Friday, and remind me to prepare my quarterly report by end of month — that one's critical") and the system automatically:

- Understands the **intent** (create? update? query?)
- **Decomposes** the input into individual structured tasks
- **Deduplicates** against already-existing tasks
- **Validates and assigns priorities** based on deadlines and workload
- **Executes the database operations** (insert/update/delete)
- Returns a summary of what was done

The pipeline is a sequential multi-agent system built with **LangGraph**, where each agent is an async node that reads from and writes to a shared state object. The frontend is a **Streamlit** multi-page app. The backend is **FastAPI** with **MongoDB Atlas** for persistence.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Browser / Streamlit :8501                    │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────┐  │
│  │  Landing /   │  │  Dashboard   │  │Assistant │  │ Settings  │  │
│  │  Auth Gate   │  │  (Task View) │  │(Voice/   │  │(Prefs /   │  │
│  │              │  │              │  │ Text UI) │  │ Export)   │  │
│  └──────────────┘  └──────────────┘  └──────────┘  └───────────┘  │
│                         │ HTTP + JWT Bearer token                   │
└─────────────────────────┼───────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────────┐
│                       FastAPI Backend :8000                          │
│                                                                     │
│  /auth/*   /tasks/*   /voice/transcribe   /voice/process            │
│                                                                     │
│       ┌─────────────────────────────────────────────┐              │
│       │         LangGraph Agent Pipeline             │              │
│       │                                             │              │
│       │  ┌──────────┐  ┌──────────────┐             │              │
│       │  │  Intent  │─▶│Decomposition │             │              │
│       │  │  Agent   │  │    Agent     │             │              │
│       │  └──────────┘  └──────┬───────┘             │              │
│       │                       │                     │              │
│       │                ┌──────▼───────┐             │              │
│       │                │    Dedup     │             │              │
│       │                │    Agent     │             │              │
│       │                └──────┬───────┘             │              │
│       │                       │                     │              │
│       │                ┌──────▼───────┐             │              │
│       │                │Prioritization│             │              │
│       │                │    Agent     │             │              │
│       │                └──────┬───────┘             │              │
│       │                       │                     │              │
│       │                ┌──────▼───────┐             │              │
│       │                │   Execute    │             │              │
│       │                │    Node      │             │              │
│       │                └─────────────┘             │              │
│       └─────────────────────────────────────────────┘              │
│                                                                     │
└──────────────┬──────────────────────────────────┬───────────────────┘
               │                                  │
┌──────────────▼────────┐            ┌────────────▼──────────────────┐
│   MongoDB Atlas        │            │       OpenAI APIs              │
│                        │            │                               │
│  ● users collection    │            │  ● Whisper-1 (transcription)  │
│  ● tasks collection    │            │  ● GPT-4o-mini (all agents)   │
└────────────────────────┘            └───────────────────────────────┘
```

---

## 3. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Streamlit | Multi-page web UI, session state, audio input |
| **Backend** | FastAPI | REST API, dependency injection, async request handling |
| **Agents** | LangGraph | StateGraph for sequential agent pipeline |
| **LLM** | GPT-4o-mini (OpenAI) | All 4 agent reasoning stages |
| **Speech-to-Text** | OpenAI Whisper-1 | Audio file → transcript |
| **Database** | MongoDB Atlas | User + task persistence (Motor async driver) |
| **Auth** | JWT (python-jose) + bcrypt | Bearer token auth, password hashing |
| **Date Parsing** | parsedatetime | Natural language date resolution in tools |
| **Config** | pydantic-settings | `.env` → typed Settings class |
| **Testing** | pytest + httpx | API + agent unit tests |
| **Deployment** | Docker Compose | Multi-service local orchestration |

---

## 4. Directory Structure

```
thought2do/
│
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, router mounting
│   │   ├── config.py                # pydantic-settings: reads .env
│   │   ├── dependencies.py          # Motor DB client, JWT get_current_user()
│   │   │
│   │   ├── agents/                  # LangGraph multi-agent pipeline
│   │   │   ├── __init__.py          # parse_llm_json(), invoke_json(), invoke_json_with_tools()
│   │   │   ├── state.py             # AgentState TypedDict (shared pipeline memory)
│   │   │   ├── graph.py             # StateGraph definition + process_voice_input() entry point
│   │   │   ├── tools.py             # resolve_date() LangChain tool
│   │   │   ├── intent_agent.py      # Node: intent classification
│   │   │   ├── decomposition_agent.py  # Node: task extraction + date resolution
│   │   │   ├── dedup_agent.py       # Node: duplicate detection
│   │   │   └── prioritization_agent.py # Node: priority validation
│   │   │
│   │   ├── prompts/                 # System prompts for each agent
│   │   │   ├── intent_prompt.py
│   │   │   ├── decomposition_prompt.py
│   │   │   ├── dedup_prompt.py
│   │   │   └── prioritization_prompt.py
│   │   │
│   │   ├── models/                  # Pydantic request/response schemas
│   │   │   ├── user.py              # UserRegister, UserLogin, UserResponse
│   │   │   └── task.py              # TaskCreate, TaskUpdate, TaskResponse + enums
│   │   │
│   │   ├── routers/                 # FastAPI route handlers
│   │   │   ├── auth.py              # /auth/register, /auth/login, /auth/me
│   │   │   ├── tasks.py             # /tasks CRUD
│   │   │   └── voice.py             # /voice/transcribe, /voice/process
│   │   │
│   │   └── services/                # Business logic (no HTTP knowledge)
│   │       ├── auth_service.py      # bcrypt hashing, JWT encode/decode
│   │       ├── task_service.py      # MongoDB CRUD, priority-sorted aggregation
│   │       ├── voice_service.py     # OpenAI Whisper wrapper
│   │       └── vector_service.py    # Pinecone stub (optional, silent no-op)
│   │
│   ├── tests/
│   │   ├── conftest.py              # pytest fixtures: test DB, client, auth token
│   │   ├── test_agents.py           # Intent/decomp/dedup/pipeline unit tests
│   │   ├── test_voice.py            # Voice transcription & processing tests
│   │   ├── test_tasks.py            # Task CRUD & filtering tests
│   │   └── evaluation.py            # Standalone eval harness (not pytest)
│   └── requirements.txt
│
├── frontend/
│   ├── app.py                       # Entry: auth gate, landing, home
│   ├── pages/
│   │   ├── 1_Dashboard.py           # Task analytics, CRUD, 4-tab layout
│   │   ├── 2_Assistant.py           # Voice/text chat interface
│   │   ├── 3_Demo.py                # Pipeline visualization
│   │   └── 4_Settings.py            # Preferences, export, stats
│   ├── components/
│   │   ├── auth_forms.py            # Login + register form components
│   │   ├── task_card.py             # Styled task card HTML component
│   │   ├── voice_recorder.py        # Audio input widget abstraction
│   │   └── sidebar.py               # Filters + stats sidebar
│   └── utils/
│       ├── api_client.py            # HTTP client for all backend calls
│       ├── theme.py                 # Dark/light CSS generation
│       └── page.py                  # Page setup helpers
│
├── .env                             # Secrets (gitignored)
├── .env.example                     # Template for .env
├── docker-compose.yml               # Multi-service orchestration
├── Makefile                         # Dev workflow shortcuts
└── README.md
```

---

## 5. The Multi-Agent Pipeline

The core intelligence of Thought2Do is a **4-agent LangGraph pipeline** that runs every time a user submits voice or text input. The pipeline is sequential: each agent reads from the shared state, does its reasoning, and writes its output fields back. LangGraph merges partial updates automatically.

All 4 agents call **GPT-4o-mini** (temperature=0 for determinism). Each agent has a dedicated system prompt in `backend/app/prompts/`.

### 5.1 State Object — The Shared Memory

Defined in `backend/app/agents/state.py` as a `TypedDict`:

```python
class AgentState(TypedDict):
    transcript:        str                # Raw text from user (voice or typed)
    user_id:           str                # MongoDB ObjectId of the logged-in user
    existing_tasks:    List[dict]         # User's current active tasks (context)
    intent:            Optional[str]      # "CREATE" | "UPDATE" | "DELETE" | "QUERY" | "MIXED"
    extracted_tasks:   List[dict]         # Output of decomposition agent
    dedup_results:     List[dict]         # Output of dedup agent (with recommendations)
    final_tasks:       List[dict]         # Output of prioritization agent
    actions_taken:     List[dict]         # Log of actual DB operations performed
    reasoning_log:     List[str]          # Chain-of-thought from each agent
    current_datetime:  str                # ISO timestamp (set at pipeline start)
    error:             Optional[str]      # Set on hard failures; stops pipeline
```

**Key insight:** `existing_tasks` is fetched once at pipeline start and passed to every agent. This lets each agent understand "what already exists" for the user — critical for dedup and intent classification.

---

### 5.2 Agent 1 — Intent Classifier

**File:** `backend/app/agents/intent_agent.py`  
**Prompt:** `backend/app/prompts/intent_prompt.py`  
**Tools used:** None (pure LLM reasoning)

**What it does:** Reads the raw transcript and classifies the user's high-level intent into one of 5 categories.

**Intent categories:**
| Intent | Meaning | Example |
|--------|---------|---------|
| `CREATE` | Add new tasks | "Schedule a dentist appointment" |
| `UPDATE` | Modify existing tasks | "Mark my gym task as done" |
| `DELETE` | Remove tasks | "Remove the grocery run task" |
| `QUERY` | List/search tasks | "What do I have due this week?" |
| `MIXED` | Multiple intents in one statement | "Cancel gym and add a run instead" |

**Prompt system message structure:**
```
You are an intent classification assistant for a task management system.

Given a voice transcript, classify the user's intent as one of:
  - CREATE: user wants to add new tasks
  - UPDATE: user wants to modify existing tasks  
  - DELETE: user wants to remove tasks
  - QUERY: user wants to view/search tasks
  - MIXED: transcript contains multiple distinct intents

Edge cases to handle:
  - "I already did X" → UPDATE (mark complete), NOT DELETE
  - "Can you remind me about X?" → QUERY if X exists, CREATE if not
  - "Change X to Y" → UPDATE
  - Ambiguous → lean toward CREATE if new thing mentioned

You have access to the user's existing tasks:
{existing_tasks}

Return ONLY valid JSON:
{
  "intent": "CREATE|UPDATE|DELETE|QUERY|MIXED",
  "confidence": 0.0–1.0,
  "reasoning": "brief explanation",
  "sub_intents": [{"intent": "...", "segment": "portion of transcript"}]
}
```

**Output fields written to state:**
- `state["intent"]` — the classified intent string
- `state["reasoning_log"]` — appends the reasoning text

**Error handling:** On LLM call failure or invalid JSON output, sets `state["error"]` and returns early. The LangGraph conditional routing will not reach subsequent agents.

---

### 5.3 Agent 2 — Task Decomposition

**File:** `backend/app/agents/decomposition_agent.py`  
**Prompt:** `backend/app/prompts/decomposition_prompt.py`  
**Tools used:** `resolve_date(phrase, anchor_iso)` — LangChain tool for calendar math

**What it does:** Takes the transcript + intent and extracts individual structured task objects. This is where natural language becomes structured data.

**The `resolve_date` Tool:**

```python
# backend/app/agents/tools.py
@tool
def resolve_date(phrase: str, anchor_iso: str) -> str:
    """
    Resolve a natural language date/time phrase to an ISO 8601 datetime string.
    
    Args:
        phrase:     Natural language like "next Thursday", "in 3 days", "end of month"
        anchor_iso: ISO datetime string to resolve relative dates against (NOW)
    
    Returns:
        ISO 8601 datetime string, or "ERROR: ..." if unparseable
    """
    cal = parsedatetime.Calendar()      # Thread-safe singleton
    anchor = datetime.fromisoformat(anchor_iso)
    time_struct, status = cal.parse(phrase, anchor.timetuple())
    if status == 0:
        return f"ERROR: could not parse '{phrase}'"
    return datetime(*time_struct[:6]).isoformat()
```

**Why a tool?** LLMs are notoriously bad at calendar math ("next Thursday from April 24" = April 30). By giving the LLM a reliable tool to call, the pipeline resolves dates with deterministic calendar logic instead of hallucinated dates.

**Tool-calling flow** (in `invoke_json_with_tools()`):
1. Send user message + system prompt + tools=[resolve_date] to GPT-4o-mini
2. LLM responds with a tool call: `resolve_date(phrase="next Friday", anchor_iso="2026-04-24T...")`
3. Python executes `resolve_date()`, gets back `"2026-05-01T00:00:00"`
4. Feed result back as a `ToolMessage`
5. LLM continues and may call the tool again (up to 5 iterations)
6. When LLM returns final content (no more tool calls), parse as JSON

**Prompt system message structure:**
```
You are a task extraction assistant for a voice-driven task manager.

Current datetime: {current_datetime}
User's existing tasks: {existing_tasks}

Given a classified transcript (intent + text), extract individual tasks.

For each task:
  - title: concise action phrase (verb + object, e.g. "Book dentist appointment")
  - description: any extra detail from the transcript
  - category: Work | Personal | Health | Finance | Education | General
    (infer from context: "report" → Work, "gym" → Health, "grocery" → Personal)
  - priority: Critical | High | Medium | Low
    (infer from urgency words: "urgent/ASAP" → Critical, "soon/need to" → High,
     default → Medium, "whenever" → Low)
  - deadline: call resolve_date() tool for any date mentioned, else null
  - tags: relevant keywords from the transcript
  - action: create | update | delete | query (aligned with overall intent)
  - update_target_id: if action=update/delete, the existing task id to target
  - update_fields: if action=update, the fields and values to change

Return ONLY valid JSON:
{
  "tasks": [...],
  "reasoning": "explanation of extraction decisions"
}
```

**Output fields written to state:**
- `state["extracted_tasks"]` — list of structured task dicts

**Conditional routing:** If `intent == "QUERY"`, the LangGraph graph skips this node entirely and routes directly to the execute node.

---

### 5.4 Agent 3 — Deduplication

**File:** `backend/app/agents/dedup_agent.py`  
**Prompt:** `backend/app/prompts/dedup_prompt.py`  
**Tools used:** None

**What it does:** Compares each extracted task against the user's existing tasks to prevent duplicates. Rather than a simple exact-match, it uses semantic similarity reasoning.

**Classification categories:**
| Status | Meaning | Recommendation |
|--------|---------|---------------|
| `unique` | No match found | `create` — insert as new |
| `duplicate` | Near-identical task exists | `skip` — don't insert |
| `related` | Similar but different enough | `merge` or `update` — enrich existing |

**Prompt system message structure:**
```
You are a deduplication assistant for a task manager.

User's existing tasks (check against these):
{existing_tasks}

For each incoming task, decide if it's:
  - unique: no similar task exists → create
  - duplicate: same task already exists → skip
  - related: similar task exists, new info should be merged → merge/update

Similarity rules:
  - Same title/intent AND same deadline → duplicate
  - Same intent, different deadline → related (update deadline)
  - Superset or subset of existing task → related (merge tags/description)
  - Entirely different → unique

Return ONLY valid JSON:
{
  "results": [
    {
      "task": {original task object},
      "status": "unique|duplicate|related",
      "matched_existing_id": "task_id or null",
      "recommendation": "create|skip|merge|update|delete",
      "merge_fields": {fields to merge into existing task},
      "reasoning": "brief explanation"
    }
  ]
}
```

**Output fields written to state:**
- `state["dedup_results"]` — list of result objects with status + recommendation

---

### 5.5 Agent 4 — Prioritization

**File:** `backend/app/agents/prioritization_agent.py`  
**Prompt:** `backend/app/prompts/prioritization_prompt.py`  
**Tools used:** None

**What it does:** Takes the dedup-approved tasks and validates/adjusts their priorities based on:
- **Deadline proximity** — a "Low" priority task due tomorrow probably needs upgrading
- **Workload balance** — if user has 5 "Critical" tasks, does a 6th really belong there?
- **Cross-task consistency** — suggest re-prioritizing existing tasks if new context changes their relative importance

**Pre-processing before LLM call:**
1. Drop tasks where `recommendation == "skip"` (duplicates)
2. For `related`/`merge` tasks, merge `merge_fields` into the task view before sending to LLM
3. Strip dedup metadata (internal fields) from the LLM input (cleaner prompt)

**Prompt system message structure:**
```
You are a priority validation assistant for a task manager.

Current datetime: {current_datetime}
User's existing tasks: {existing_tasks}

For each incoming task, validate the assigned priority considering:
  1. Deadline proximity:
     - Due within 24h → at least High
     - Due within 3 days → at least Medium
     - Overdue → Critical
  2. Explicit urgency words override deadline rules
  3. Workload: if >3 Critical tasks exist, be selective
  4. Consider re-prioritizing existing tasks if new task context changes balance

Return ONLY valid JSON:
{
  "tasks": [
    {
      "task": {task object with final priority},
      "priority_changed": true|false,
      "original_priority": "...",
      "new_priority": "...",
      "reasoning": "..."
    }
  ],
  "reprioritize_existing": [
    {
      "task_id": "...",
      "current_priority": "...",
      "suggested_priority": "...",
      "reasoning": "..."
    }
  ],
  "overall_reasoning": "summary"
}
```

**Output fields written to state:**
- `state["final_tasks"]` — list of task dicts with final validated priorities

**Fail-open design:** If the LLM call fails (timeout, parse error), the node returns `final_tasks = eligible_tasks` (the incoming tasks with their existing priorities). The pipeline never fails because of prioritization.

---

### 5.6 Execution Node — Deterministic CRUD

**File:** `backend/app/agents/graph.py` (the `_make_execute_node` closure)  
**Not an LLM agent** — this is pure Python logic that translates the pipeline's decisions into actual database operations.

**Structure:** Created as a closure factory to capture the `db` dependency:
```python
def _make_execute_node(db):
    async def execute_node(state: AgentState) -> dict:
        ...
    return execute_node
```

**Dispatch logic per task:**

```
For each task in state["final_tasks"]:
  ├── action == "create"
  │     → TaskService.create_task(TaskCreate(**task_fields), user_id)
  │     → log: {"action": "create", "task_id": ..., "title": ...}
  │
  ├── action == "update"  (or dedup_recommendation == "merge"/"update")
  │     → resolve target: use update_target_id or matched_existing_id
  │     → apply: update_fields merged with dedup_merge_fields
  │     → TaskService.update_task(task_id, user_id, TaskUpdate(**merged_fields))
  │     → log: {"action": "update", "task_id": ..., "title": ...}
  │
  ├── action == "delete"
  │     → resolve target: update_target_id
  │     → TaskService.delete_task(task_id, user_id)
  │     → log: {"action": "delete", "task_id": ..., "title": ...}
  │
  └── action == "query"
        → extract filter fields from update_fields
        → TaskService.get_tasks(user_id, status=..., category=..., priority=...)
        → log: {"action": "query", "results": [...tasks...]}
```

**QUERY short-circuit:** If `intent == "QUERY"` and no extracted tasks exist (e.g., "What's on my list?"), the node directly calls `TaskService.get_tasks(user_id)` and returns all active tasks.

**Error isolation:** Each task operation is wrapped in its own try/except. A single failed update doesn't stop the creation of other tasks.

**Output fields written to state:**
- `state["actions_taken"]` — complete log of all operations with results

---

### 5.7 LangGraph Wiring

**File:** `backend/app/agents/graph.py`

```python
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("intent",         intent_node)
workflow.add_node("decomposition",  decomposition_node)
workflow.add_node("dedup",          dedup_node)
workflow.add_node("prioritization", prioritization_node)
workflow.add_node("execute",        _make_execute_node(db))

# Edges
workflow.add_edge(START,             "intent")
workflow.add_conditional_edges(
    "intent",
    _route_after_intent,              # QUERY → "execute", else → "decomposition"
    {"decomposition": "decomposition", "execute": "execute"}
)
workflow.add_edge("decomposition",   "dedup")
workflow.add_edge("dedup",           "prioritization")
workflow.add_edge("prioritization",  "execute")
workflow.add_edge("execute",         END)

graph = workflow.compile()
```

**Routing logic:**
```python
def _route_after_intent(state: AgentState) -> str:
    return "execute" if state["intent"] == "QUERY" else "decomposition"
```

This means QUERY requests skip decomposition, dedup, and prioritization entirely — they go straight to the execute node which fetches tasks.

**Full pipeline flow:**
```
START
  ↓
intent_node
  ↓ (if CREATE/UPDATE/DELETE/MIXED)      ↓ (if QUERY)
decomposition_node                     execute_node ──→ END
  ↓
dedup_node
  ↓
prioritization_node
  ↓
execute_node
  ↓
END
```

---

## 6. Data Flow — End to End

Here's the complete journey of a user request through the system:

```
USER SPEAKS: "Add a dentist appointment for next Friday, and mark my gym 
             task as done. What's due this week?"

═══════════════════════════════════════════════════════════════════
STEP 1: AUDIO CAPTURE (Frontend — Assistant page)
═══════════════════════════════════════════════════════════════════

  Streamlit st.audio_input() widget
        ↓ (audio bytes: WebM/WAV/MP3)
  APIClient.process_voice(audio_bytes=..., filename="recording.webm")
        ↓ HTTP POST /voice/process (multipart form, Bearer JWT)

═══════════════════════════════════════════════════════════════════
STEP 2: TRANSCRIPTION (Backend — /voice/process router)
═══════════════════════════════════════════════════════════════════

  voice.py router detects audio file in request
        ↓
  VoiceService.transcribe(audio_file)
        ↓ writes to temp file
  OpenAI Whisper-1 API call:
    POST https://api.openai.com/v1/audio/transcriptions
    model=whisper-1, response_format=verbose_json
        ↓ returns
  {
    "transcript": "Add a dentist appointment for next Friday, and mark 
                   my gym task as done. What's due this week?",
    "language": "en",
    "duration": 4.2
  }

═══════════════════════════════════════════════════════════════════
STEP 3: CONTEXT LOADING (graph.py — process_voice_input())
═══════════════════════════════════════════════════════════════════

  TaskService.get_tasks_for_context(user_id, limit=20)
        ↓ MongoDB aggregation:
          db.tasks.aggregate([
            {"$match": {"user_id": user_id, "status": {"$in": ["pending","in_progress"]}}},
            {"$sort": {"priority": 1, "deadline": 1}},
            {"$limit": 20},
            {"$project": {id, title, category, priority, deadline, status, tags}}
          ])
        ↓ returns existing_tasks:
  [
    {"id": "abc123", "title": "Morning gym session", "priority": "Medium", 
     "status": "pending", "category": "Health"},
    {"id": "def456", "title": "Q1 report", "priority": "High", 
     "deadline": "2026-04-30", "status": "in_progress"}
  ]

═══════════════════════════════════════════════════════════════════
STEP 4: LANGGRAPH PIPELINE (all agents run sequentially)
═══════════════════════════════════════════════════════════════════

  Initial AgentState:
  {
    "transcript": "Add a dentist appointment...",
    "user_id": "user_objectid",
    "existing_tasks": [...2 tasks above...],
    "intent": None,
    "extracted_tasks": [],
    "dedup_results": [],
    "final_tasks": [],
    "actions_taken": [],
    "reasoning_log": [],
    "current_datetime": "2026-04-24T10:30:00",
    "error": None
  }

  ─── AGENT 1: Intent Node ──────────────────────────────────────
  
  GPT-4o-mini called with:
    system: INTENT_SYSTEM_PROMPT (with existing_tasks injected)
    user:   "Transcript:\nAdd a dentist appointment for next Friday, 
             and mark my gym task as done. What's due this week?"
  
  GPT-4o-mini responds:
  {
    "intent": "MIXED",
    "confidence": 0.97,
    "reasoning": "Transcript contains three distinct intents: CREATE 
                  (dentist), UPDATE (gym done), QUERY (due this week)",
    "sub_intents": [
      {"intent": "CREATE", "segment": "Add a dentist appointment for next Friday"},
      {"intent": "UPDATE", "segment": "mark my gym task as done"},
      {"intent": "QUERY",  "segment": "What's due this week?"}
    ]
  }

  State updated: intent = "MIXED"

  ─── AGENT 2: Decomposition Node ───────────────────────────────
  
  GPT-4o-mini (with tools) called with:
    system: DECOMPOSITION_SYSTEM_PROMPT
    user:   "Classified intent: MIXED\nTranscript:\nAdd a dentist..."
    tools:  [resolve_date]
  
  LLM calls tool: resolve_date("next Friday", "2026-04-24T10:30:00")
  Tool returns:   "2026-05-01T00:00:00"
  
  LLM final response:
  {
    "tasks": [
      {
        "title": "Book dentist appointment",
        "description": null,
        "category": "Health",
        "priority": "Medium",
        "deadline": "2026-05-01T00:00:00",
        "tags": ["dentist", "appointment"],
        "action": "create",
        "update_target_id": null,
        "update_fields": {}
      },
      {
        "title": "Morning gym session",
        "description": null,
        "category": "Health",
        "priority": "Medium",
        "deadline": null,
        "tags": ["gym"],
        "action": "update",
        "update_target_id": "abc123",
        "update_fields": {"status": "completed"}
      },
      {
        "title": "tasks due this week",
        "description": "what is due this week",
        "category": "General",
        "priority": "Medium",
        "deadline": null,
        "tags": [],
        "action": "query",
        "update_target_id": null,
        "update_fields": {"deadline_range": "this_week"}
      }
    ],
    "reasoning": "Extracted 3 tasks matching the 3 sub-intents..."
  }

  State updated: extracted_tasks = [3 tasks above]

  ─── AGENT 3: Dedup Node ───────────────────────────────────────
  
  GPT-4o-mini called with:
    system: DEDUP_SYSTEM_PROMPT (with existing_tasks)
    user:   JSON of extracted_tasks
  
  LLM response:
  {
    "results": [
      {
        "task": {dentist task},
        "status": "unique",
        "matched_existing_id": null,
        "recommendation": "create",
        "merge_fields": {},
        "reasoning": "No dentist task exists"
      },
      {
        "task": {gym update task},
        "status": "duplicate",
        "matched_existing_id": "abc123",
        "recommendation": "update",
        "merge_fields": {"status": "completed"},
        "reasoning": "Matches existing 'Morning gym session' task"
      },
      {
        "task": {query task},
        "status": "unique",
        "matched_existing_id": null,
        "recommendation": "create",  ← (query tasks always pass through)
        "merge_fields": {},
        "reasoning": "Query intent, no dedup needed"
      }
    ]
  }

  State updated: dedup_results = [3 results above]

  ─── AGENT 4: Prioritization Node ──────────────────────────────
  
  Eligible tasks (non-skip): dentist (create) + gym (update) + query
  
  GPT-4o-mini called with:
    system: PRIORITIZATION_SYSTEM_PROMPT
    user:   JSON of eligible tasks
  
  LLM response:
  {
    "tasks": [
      {
        "task": {dentist task with priority "High"},  ← upgraded! (1 week away)
        "priority_changed": true,
        "original_priority": "Medium",
        "new_priority": "High",
        "reasoning": "Deadline in 7 days warrants High priority"
      },
      {
        "task": {gym update, priority "Medium"},
        "priority_changed": false,
        "original_priority": "Medium",
        "new_priority": "Medium",
        "reasoning": "No deadline, status update only"
      },
      {
        "task": {query, priority "Medium"},
        "priority_changed": false,
        ...
      }
    ],
    "reprioritize_existing": [],
    "overall_reasoning": "Dentist appointment upgraded due to 7-day deadline"
  }

  State updated: final_tasks = [3 tasks with final priorities]

  ─── EXECUTE NODE ──────────────────────────────────────────────
  
  Task 1 (create): dentist appointment
    → TaskService.create_task({
        title: "Book dentist appointment",
        category: "Health", priority: "High",
        deadline: "2026-05-01", tags: ["dentist", "appointment"]
      }, user_id="user_objectid")
    → MongoDB: db.tasks.insert_one({...})
    → actions_taken: {action:"create", task_id:"ghi789", title:"Book dentist..."}
  
  Task 2 (update): gym session
    → TaskService.update_task("abc123", user_id, TaskUpdate(status="completed"))
    → MongoDB: db.tasks.update_one({_id: ObjectId("abc123")}, {$set: {status:"completed"}})
    → actions_taken: {action:"update", task_id:"abc123", title:"Morning gym session"}
  
  Task 3 (query): due this week
    → TaskService.get_tasks(user_id, deadline_range="this_week")
    → MongoDB: db.tasks.find({user_id:..., deadline: {$gte: today, $lte: +7days}})
    → actions_taken: {action:"query", results:[Q1 report task]}

═══════════════════════════════════════════════════════════════════
STEP 5: RESPONSE ASSEMBLY (graph.py — _response_from_actions())
═══════════════════════════════════════════════════════════════════

  {
    "transcript": "Add a dentist appointment...",
    "tasks_created": [{"id":"ghi789", "title":"Book dentist appointment", ...}],
    "tasks_updated": [{"id":"abc123", "title":"Morning gym session", ...}],
    "tasks_deleted": [],
    "tasks_queried": [{"id":"def456", "title":"Q1 report", ...}],
    "agent_reasoning": [
      "Intent: MIXED (confidence: 0.97). Contains 3 sub-intents...",
      "Decomposed into 3 tasks. Dentist deadline resolved to 2026-05-01...",
      "Dentist: UNIQUE. Gym: matched to abc123. Query passed through.",
      "Dentist priority upgraded Medium→High (7-day deadline)..."
    ]
  }

═══════════════════════════════════════════════════════════════════
STEP 6: FRONTEND DISPLAY (Assistant page)
═══════════════════════════════════════════════════════════════════

  Streamlit renders:
  
  ✅ Created (1):
  ┌─────────────────────────────────────────┐
  │ 🟠 Book dentist appointment             │
  │ Health • High • Due May 1               │
  │ Tags: dentist, appointment              │
  └─────────────────────────────────────────┘
  
  ✏️ Updated (1):
  ┌─────────────────────────────────────────┐
  │ ⚪ Morning gym session           ✅      │
  │ Health • Medium • Completed             │
  └─────────────────────────────────────────┘
  
  👁️ Queried (1):
  ┌─────────────────────────────────────────┐
  │ 🔵 Q1 report                            │
  │ Work • High • Due Apr 30                │
  └─────────────────────────────────────────┘
  
  ▸ Agent Reasoning [expand to see chain-of-thought]
```

---

## 7. Backend API Reference

### Auth Endpoints

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| `POST` | `/auth/register` | No | `{email, password, name}` | `UserResponse` (201) |
| `POST` | `/auth/login` | No | `{email, password}` | `{access_token, token_type, user}` |
| `GET` | `/auth/me` | JWT | — | `UserResponse` |

### Task Endpoints

| Method | Path | Auth | Query Params | Response |
|--------|------|------|-------------|----------|
| `POST` | `/tasks` | JWT | — | `TaskResponse` (201) |
| `GET` | `/tasks` | JWT | `status`, `category`, `priority`, `skip`, `limit` | `TaskListResponse` |
| `GET` | `/tasks/{id}` | JWT | — | `TaskResponse` |
| `PUT` | `/tasks/{id}` | JWT | — | `TaskResponse` |
| `DELETE` | `/tasks/{id}` | JWT | — | 204 No Content |

### Voice Endpoints

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| `POST` | `/voice/transcribe` | JWT | Multipart audio file | `{transcript, language, duration}` |
| `POST` | `/voice/process` | JWT | Multipart audio OR `{transcript: "..."}` | `VoiceProcessResponse` |

**VoiceProcessResponse shape:**
```json
{
  "transcript": "string",
  "tasks_created": [TaskResponse, ...],
  "tasks_updated": [TaskResponse, ...],
  "tasks_deleted": [TaskResponse, ...],
  "tasks_queried": [TaskResponse, ...],
  "agent_reasoning": ["string", ...]
}
```

---

## 8. Database Schemas

### `users` Collection

```json
{
  "_id":             "ObjectId",
  "email":           "string (unique index)",
  "name":            "string",
  "hashed_password": "string (bcrypt, 60 chars)",
  "created_at":      "datetime (UTC)"
}
```

### `tasks` Collection

```json
{
  "_id":            "ObjectId",
  "user_id":        "string (ObjectId ref → users._id)",
  "title":          "string",
  "description":    "string | null",
  "category":       "Work | Personal | Health | Finance | Education | General",
  "priority":       "Critical | High | Medium | Low",
  "deadline":       "datetime | null",
  "status":         "pending | in_progress | completed | cancelled",
  "tags":           ["string"],
  "parent_task_id": "string | null  (for subtask hierarchy)",
  "source":         "voice | manual | decomposed",
  "created_at":     "datetime (UTC)",
  "updated_at":     "datetime (UTC)"
}
```

**Priority sort in MongoDB aggregation:**

`TaskService.get_tasks()` uses an aggregation pipeline with an `$addFields` stage to compute a numeric sort rank:

```python
_PRIORITY_ORDER_STAGE = {
    "$addFields": {
        "_priority_rank": {
            "$switch": {
                "branches": [
                    {"case": {"$eq": ["$priority", "Critical"]}, "then": 0},
                    {"case": {"$eq": ["$priority", "High"]},     "then": 1},
                    {"case": {"$eq": ["$priority", "Medium"]},   "then": 2},
                    {"case": {"$eq": ["$priority", "Low"]},      "then": 3},
                ],
                "default": 4
            }
        }
    }
}
```

Then sorts by: `_priority_rank ASC, deadline ASC (nulls last), created_at DESC`

---

## 9. Frontend Pages

### `app.py` — Landing / Auth Gate

**Session state initialized:**
```python
st.session_state.token            = None
st.session_state.user             = None
st.session_state.theme            = "dark"
st.session_state.filter_status    = "All"
st.session_state.filter_category  = "All"
st.session_state.filter_priority  = "All"
st.session_state.default_category = "General"
st.session_state.default_priority = "Medium"
```

**Logic:** If no token → show landing page with Login/Register tabs. If token present → show sidebar (user name, theme toggle, logout) + home page (3 cards linking to Dashboard, Assistant, Demo).

---

### `pages/1_Dashboard.py` — Task Analytics

**4-tab layout:**

| Tab | Content |
|-----|---------|
| **Overview** | 4 metric cards (Total Active, Due Today, Overdue, Completed This Week) + pie/bar charts |
| **By Priority** | Tasks grouped under 🔴 Critical / 🟠 High / 🔵 Medium / ⚪ Low headers |
| **By Category** | Tasks grouped under 💼 Work / 🏠 Personal / 🏃 Health / 💰 Finance / 📚 Education / 📌 General |
| **By Time** | Tasks bucketed: Overdue → Today → Tomorrow → This Week → Later → No Deadline → Completed |

**Calls:** `GET /tasks` with filter params from sidebar state. Manual add/edit/delete buttons call `POST /tasks`, `PUT /tasks/{id}`, `DELETE /tasks/{id}`.

---

### `pages/2_Assistant.py` — Voice/Text Interface

**Session state:**
```python
st.session_state.chat_messages       = []   # message history
st.session_state.pending_transcript  = None
st.session_state.audio_reset_counter = 0
st.session_state.chat_input_draft    = ""
```

**Two-column layout:**
- **Left:** Voice recorder widget OR text area, then "Process" button
- **Right:** Pipeline visualization (4 stages with spinners → checkmarks as each agent completes)

**Flow:**
1. User records audio → transcribe via `POST /voice/transcribe` → show transcript in editable expander
2. User clicks Process → `POST /voice/process` with transcript
3. Display task cards for created/updated/deleted/queried tasks
4. Show agent reasoning in collapsible expander
5. Append to chat history in session state

---

### `pages/3_Demo.py` — Pipeline Visualization

**Purpose:** Step-by-step walkthrough of the agent pipeline for demonstration/educational purposes. Shows each agent stage with input → output visualization.

---

### `pages/4_Settings.py` — Preferences & Export

**Sections:**
- **Profile:** Name, email (read-only), member since date
- **Appearance:** Dark/light theme toggle with live preview
- **Task Defaults:** Default category + priority for manual task creation
- **Voice Settings:** Toggle between `st.audio_input()` and `st.file_uploader()` fallback
- **Data Management:** Export all tasks as JSON download, bulk-delete completed tasks (with confirmation dialog)
- **About:** App version, tech stack credits

---

### `components/task_card.py` — Task Card HTML

The task card renders custom HTML via `st.markdown(..., unsafe_allow_html=True)`:

```
┌────────────────────────────────────────────────────┐  ← left border: priority color
│  Book dentist appointment              [✅ Created]  │     Critical = red (#EF4444)
│  ─────────────────────────────────────────────────  │     High     = orange (#F97316)
│  [Health]  🟠 High  ⚠️ Due in 7 days               │     Medium   = blue (#3B82F6)
│  Tags: dentist  appointment                         │     Low      = gray (#6B7280)
│  Source: 🎙️ voice    Status: [pending]              │
└────────────────────────────────────────────────────┘
```

**`_format_deadline()` logic:**
- Past deadline → `"⚠️ Overdue"` (red)
- Today → `"Due today"` (yellow)
- Tomorrow → `"Due tomorrow"` (yellow)
- 2–6 days → `"Due in N days"` (yellow if ≤3, else normal)
- 7+ days → `"Due Month Day"` (normal)

---

## 10. Services Layer

### `TaskService` (task_service.py)

The central business logic class. Instantiated per-request via FastAPI dependency injection.

```python
class TaskService:
    def __init__(self, db):
        self.collection = db.tasks
    
    async def create_task(task: TaskCreate, user_id: str) -> TaskResponse
    async def get_tasks(user_id, status?, category?, priority?, skip, limit) -> TaskListResponse
    async def get_task(task_id: str, user_id: str) -> TaskResponse
    async def update_task(task_id, user_id, updates: TaskUpdate) -> TaskResponse
    async def delete_task(task_id: str, user_id: str) -> bool
    async def get_tasks_for_context(user_id, limit=20) -> List[dict]
```

Key detail: `get_tasks_for_context()` returns a **simplified projection** (only the fields agents need: id, title, category, priority, deadline, status, tags). This keeps the LLM prompts compact.

---

### `VoiceService` (voice_service.py)

```python
class VoiceService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def transcribe(audio_file: UploadFile) -> dict:
        # Validates format (webm/wav/mp3/m4a/ogg/mpeg) and size (≤25MB)
        # Writes to temp file, calls Whisper-1
        # Returns {transcript, language, duration}
```

---

### `AuthService` (auth_service.py)

Stateless functions (no class needed):

```python
def hash_password(password: str) -> str        # bcrypt via passlib
def verify_password(plain: str, hashed: str) -> bool
def create_access_token(user_id: str, email: str) -> str   # JWT, 24h expiry
def decode_access_token(token: str) -> dict                # raises ValueError on invalid
```

---

## 11. LLM Helper Utilities

Defined in `backend/app/agents/__init__.py`. These handle all LLM calls across the pipeline.

### `parse_llm_json(response_text: str) -> dict`
Strips markdown code fences (` ```json `) from LLM output, then calls `json.loads()`. Raises `ValueError` with the first 200 chars of the response if parsing fails.

### `invoke_json(system_prompt, user_message, *, retries=1) -> dict`
```
1. Create ChatOpenAI(model="gpt-4o-mini", temperature=0)
2. await asyncio.wait_for(llm.ainvoke([system, user]), timeout=30)
3. parse_llm_json(response.content)
4. On ValueError or TimeoutError: retry once
5. On 2nd failure: raise RuntimeError("LLM call failed after N attempts")
```

### `invoke_json_with_tools(system_prompt, user_message, tools, *, max_tool_iterations=5, retries=1) -> dict`
```
1. Create ChatOpenAI with tools bound: llm.bind_tools(tools)
2. Enter tool-calling loop (max 5 iterations):
   a. Call LLM
   b. If response has tool_calls:
      - Execute each tool (from tools registry)
      - Append tool result as ToolMessage to messages
      - Continue loop
   c. If response has content (no tool calls):
      - parse_llm_json(response.content) → return dict
3. On parse error or timeout: retry whole exchange once
4. On 2nd failure: raise RuntimeError
```

---

## 12. Authentication System

**Registration flow:**
```
POST /auth/register {email, password, name}
  → check db.users.find_one({email}) → 400 if exists
  → hash_password(password) → bcrypt hash
  → db.users.insert_one({email, name, hashed_password, created_at})
  → return UserResponse (201)
```

**Login flow:**
```
POST /auth/login {email, password}
  → db.users.find_one({email}) → 401 if not found
  → verify_password(password, hashed_password) → 401 if wrong
  → create_access_token(user_id, email) → JWT string
  → return {access_token, token_type: "bearer", user: UserResponse}
```

**JWT structure:**
```json
{
  "sub": "user_objectid_string",
  "email": "user@example.com",
  "exp": 1714005000   ← Unix timestamp, 24h from issue
}
```

**Protected endpoint guard (`get_current_user`):**
```
Extract "Authorization: Bearer <token>" header
  → decode_access_token(token) → raises ValueError on invalid/expired
  → db.users.find_one({_id: ObjectId(payload["sub"])})
  → 401 if user not found
  → return user document dict
```

All task operations filter by `user_id` so users can never access each other's data.

---

## 13. Configuration & Environment

**`backend/app/config.py`** uses `pydantic-settings`:

```python
class Settings(BaseSettings):
    OPENAI_API_KEY:         str
    MONGODB_URI:            str
    MONGODB_DB_NAME:        str     = "thought2do"
    JWT_SECRET_KEY:         str
    JWT_ALGORITHM:          str     = "HS256"
    JWT_EXPIRATION_MINUTES: int     = 1440         # 24 hours
    PINECONE_API_KEY:       Optional[str] = None   # Optional; blank disables vector features
    PINECONE_INDEX_NAME:    Optional[str] = "thought2do-vault"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env"
    )
```

**`.env` template:**
```ini
OPENAI_API_KEY=sk-proj-...
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?appName=Thought2Do
MONGODB_DB_NAME=thought2do
JWT_SECRET_KEY=<64-char random hex>
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=1440
PINECONE_API_KEY=          # Leave blank to disable
PINECONE_INDEX_NAME=thought2do-vault
```

**Running locally:**
```bash
# Backend (from backend/ directory)
uvicorn app.main:app --reload --port 8000

# Frontend (from frontend/ directory)
streamlit run app.py --server.port 8501

# Or with Makefile
make run-backend
make run-frontend

# Or with Docker
docker compose up
```

---

## 14. Key Architectural Decisions

### 1. Sequential Pipeline, Not Parallel Agents
Each agent builds on the previous one's output (decomposition needs the intent, dedup needs the decomposed tasks). Sequential is correct here — parallelism would require rethinking the entire data flow.

### 2. GPT-4o-mini for All Agents
Single model choice keeps the system uniform and cost-effective. Temperature=0 ensures deterministic (reproducible) outputs across all agents.

### 3. Tool Calling for Date Resolution
LLMs fail at calendar math. Instead of trusting GPT-4o-mini to calculate "next Friday from April 24, 2026", the decomposition agent calls the `resolve_date()` Python function which uses `parsedatetime` — a dedicated calendar library. This eliminates a whole class of bugs.

### 4. Fail-Open Prioritization
If the prioritization LLM call fails (timeout, parse error, API outage), the node silently returns the tasks with their existing priorities rather than crashing the pipeline. Tasks still get created/updated — just without priority adjustment. The system degrades gracefully.

### 5. Dedup Recommends Merge, Not Just Skip
A simple dedup system would either create a duplicate or skip the new task. Thought2Do's dedup agent can instead recommend "merge" — adding new deadline/tags/description to an existing task. This is more useful than either extreme.

### 6. Motor Async + FastAPI Async Throughout
All database calls use `motor` (async MongoDB driver). All LLM calls use `AsyncOpenAI`. All agent nodes are `async def`. This means FastAPI can handle concurrent requests without blocking on I/O — important when each pipeline call takes 3–5 LLM round-trips.

### 7. User Isolation at Every Layer
- All MongoDB queries include `{"user_id": current_user_id}` filter
- JWT `sub` claim stores user_id; `get_current_user()` dependency resolves it on every request
- Pinecone namespaces by `user_id` (when enabled)
- No cross-user data leakage is possible by design

### 8. Streamlit Session State as Frontend Store
All client state (JWT token, user profile, task filters, theme, chat history) lives in `st.session_state`. No external state store needed. Caveat: session resets on page refresh, so users log in again.

### 9. Priority Sort via Aggregation Pipeline
String sorting of "Critical/High/Medium/Low" doesn't work alphabetically. Instead, the `get_tasks()` aggregation pipeline computes a numeric rank (0–3) via `$switch/$addFields` and sorts numerically. This is DB-side sorting — no Python sorting needed.

### 10. QUERY Short-Circuit
A QUERY intent skips 3 agent nodes (decomposition, dedup, prioritization). This makes read-only queries significantly faster and cheaper — no LLM calls needed beyond intent classification.

---

## 15. Worked Example — Full Pipeline Trace

**Input:** `"I need to finish the project proposal by Thursday — it's really urgent. Also, what are my pending tasks?"`

**Current date:** April 24, 2026 (Thursday = April 30)

```
┌─────────────────────────────────────────────────────────────────┐
│ AGENT 1: INTENT                                                 │
│                                                                 │
│ Input transcript: "I need to finish the project proposal by     │
│   Thursday — it's really urgent. Also, what are my pending..."  │
│                                                                 │
│ LLM Output:                                                     │
│ {                                                               │
│   "intent": "MIXED",                                            │
│   "confidence": 0.95,                                           │
│   "sub_intents": [                                              │
│     {"intent": "CREATE", "segment": "finish the project         │
│                          proposal by Thursday — really urgent"} │
│     {"intent": "QUERY",  "segment": "what are my pending tasks"}│
│   ]                                                             │
│ }                                                               │
│                                                                 │
│ → state.intent = "MIXED"                                        │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ AGENT 2: DECOMPOSITION                                          │
│                                                                 │
│ Tool call #1:                                                   │
│   resolve_date("Thursday", "2026-04-24T09:00:00")              │
│   → "2026-04-30T00:00:00"                                       │
│                                                                 │
│ LLM Output:                                                     │
│ {                                                               │
│   "tasks": [                                                    │
│     {                                                           │
│       "title": "Finish project proposal",                       │
│       "category": "Work",                                       │
│       "priority": "Critical",    ← inferred from "really urgent"│
│       "deadline": "2026-04-30T00:00:00",                        │
│       "tags": ["proposal", "project"],                          │
│       "action": "create"                                        │
│     },                                                          │
│     {                                                           │
│       "title": "pending tasks query",                           │
│       "category": "General",                                    │
│       "priority": "Medium",                                     │
│       "action": "query",                                        │
│       "update_fields": {"status": "pending"}                    │
│     }                                                           │
│   ]                                                             │
│ }                                                               │
│                                                                 │
│ → state.extracted_tasks = [2 tasks above]                       │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ AGENT 3: DEDUP                                                  │
│                                                                 │
│ Checks against existing tasks...                                │
│ (Assume no "project proposal" task exists yet)                  │
│                                                                 │
│ LLM Output:                                                     │
│ {                                                               │
│   "results": [                                                  │
│     {                                                           │
│       "task": {proposal task},                                  │
│       "status": "unique",                                       │
│       "recommendation": "create"                                │
│     },                                                          │
│     {                                                           │
│       "task": {query task},                                     │
│       "status": "unique",                                       │
│       "recommendation": "create"                                │
│     }                                                           │
│   ]                                                             │
│ }                                                               │
│                                                                 │
│ → state.dedup_results = [2 results, none skipped]               │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ AGENT 4: PRIORITIZATION                                         │
│                                                                 │
│ Proposal task: priority "Critical", deadline April 30           │
│ April 30 is 6 days away → Critical is already appropriate       │
│                                                                 │
│ LLM Output:                                                     │
│ {                                                               │
│   "tasks": [                                                    │
│     {                                                           │
│       "task": {proposal, priority: "Critical"},                 │
│       "priority_changed": false,                                │
│       "reasoning": "Critical priority confirmed: explicit       │
│                     'really urgent' + 6-day deadline"           │
│     },                                                          │
│     {query task, no change}                                     │
│   ],                                                            │
│   "reprioritize_existing": []                                   │
│ }                                                               │
│                                                                 │
│ → state.final_tasks = [proposal at Critical, query task]        │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ EXECUTE NODE                                                    │
│                                                                 │
│ Task 1 → CREATE:                                                │
│   db.tasks.insert_one({                                         │
│     title: "Finish project proposal",                           │
│     category: "Work", priority: "Critical",                     │
│     deadline: "2026-04-30", status: "pending",                  │
│     source: "voice", user_id: ..., tags: ["proposal","project"] │
│   })                                                            │
│   → new task_id: "xyz999"                                       │
│                                                                 │
│ Task 2 → QUERY:                                                 │
│   db.tasks.find({user_id: ..., status: "pending"})              │
│   → returns all pending tasks                                   │
│                                                                 │
│ → state.actions_taken = [                                       │
│     {action:"create", task_id:"xyz999", title:"Finish project…"}│
│     {action:"query", results:[...all pending tasks...]}         │
│   ]                                                             │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ RESPONSE                                                        │
│                                                                 │
│ {                                                               │
│   "transcript": "I need to finish the project proposal...",     │
│   "tasks_created": [                                            │
│     {id:"xyz999", title:"Finish project proposal",              │
│      category:"Work", priority:"Critical",                      │
│      deadline:"2026-04-30", status:"pending"}                   │
│   ],                                                            │
│   "tasks_updated": [],                                          │
│   "tasks_deleted": [],                                          │
│   "tasks_queried": [...all pending tasks...],                   │
│   "agent_reasoning": [                                          │
│     "Intent: MIXED with CREATE + QUERY sub-intents",            │
│     "Extracted 2 tasks; 'really urgent' → Critical priority",   │
│     "Both tasks unique; no duplicates found",                   │
│     "Critical priority confirmed for proposal (6-day deadline)" │
│   ]                                                             │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

*This document covers every major technical component of Thought2Do: the 4-agent LangGraph pipeline, data flow from browser to database, API contracts, database schemas, frontend architecture, and the key design decisions that shaped the system.*
