# Thought2Do

> **Think it. Say it. Done.**

Thought2Do is an agentic, voice-driven task management system. You speak naturally — a multi-agent LangGraph pipeline processes your utterance through Intent Classification → Task Decomposition → Deduplication → Prioritization and persists structured tasks in MongoDB. The friction of logging a task should be lower than the friction of doing the task. Thought2Do removes that friction entirely.

> **Project Status: Under Development**

---

## System Flow

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

---

## Setup

**Prerequisites:** Python 3.10+, a MongoDB Atlas cluster, an OpenAI API key. Pinecone is optional.

```bash
# 1. Clone
git clone <your-repo-url> thought2do
cd thought2do

# 2. Create .env from the template and fill in your values
cp .env.example .env
# then edit .env in your editor

# 3. Install dependencies (backend + frontend)
make install

# 4. Run the backend (terminal 1)
make run-backend
# → FastAPI at http://localhost:8000

# 5. Run the frontend (terminal 2)
make run-frontend
# → Streamlit at http://localhost:8501
```

### Useful make targets

| Target | Purpose |
|---|---|
| `make install` | Install backend + frontend dependencies |
| `make run-backend` | Start FastAPI with auto-reload on :8000 |
| `make run-frontend` | Start Streamlit on :8501 |
| `make test` | Run the pytest suite |
| `make evaluate` | Run the standalone agent-pipeline evaluation harness |
| `make docker-build` / `make docker-up` / `make docker-down` | Docker lifecycle |

---

## Tech Stack

**Backend**
- FastAPI + Uvicorn
- Pydantic v2 / pydantic-settings
- Motor (async MongoDB driver) + PyMongo
- python-jose + passlib[bcrypt] for JWT auth
- OpenAI Whisper (speech-to-text) + GPT-4o-mini (reasoning)
- LangChain + langchain-openai + LangGraph (multi-agent pipeline)
- Pinecone (optional vector store)
- httpx (HTTP client for tests/integration)

**Frontend**
- Streamlit (multi-page app, native audio input)
- requests (backend HTTP client)
- streamlit-webrtc, extra-streamlit-components, pydub

**Data**
- MongoDB Atlas (users + tasks collections, user-isolated)
- Pinecone (optional, embeddings per user namespace)

---

## Project Structure

```
thought2do/
├── backend/           # FastAPI service, agents, services, tests
│   ├── app/
│   │   ├── agents/    # LangGraph nodes: intent, decomposition, dedup, prioritization
│   │   ├── prompts/   # System prompts for each agent
│   │   ├── routers/   # HTTP routes: auth, tasks, voice
│   │   ├── services/  # Business logic: auth, task, voice, vector
│   │   └── models/    # Pydantic schemas
│   └── tests/
├── frontend/          # Streamlit multi-page app
│   ├── pages/         # Dashboard, Voice Input, Settings
│   ├── components/    # Reusable UI pieces (task card, sidebar, forms)
│   └── utils/         # API client, theme system
├── .env.example
├── Makefile
├── docker-compose.yml
└── PLAN.md            # Canonical build plan and architecture reference
```

For the full architecture reference (data models, API endpoints, LLM output contracts, UI spec), see [PLAN.md](PLAN.md).
