# Thought2Do

**Done by:** **Yohan Markose**

> **Think it. Say it. Done.**

Thought2Do is an agentic, voice-driven task management system. You speak naturally — a multi-agent LangGraph pipeline processes your utterance through Intent Classification → Task Decomposition → Deduplication → Prioritization and persists structured tasks in MongoDB. The friction of logging a task should be lower than the friction of doing the task. Thought2Do removes that friction entirely.


---

## System Flow

```
[Browser Mic / Text Input]
       │
       ▼
[Streamlit Frontend :8501]
       │ HTTPS  Bearer JWT
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
       ├── 1. Intent Agent       ──► Classifies: CREATE / UPDATE / DELETE / QUERY / MIXED
       ├── 2. Decomposition Agent ──► Extracts structured tasks, resolves dates, web enrichment
       ├── 3. Deduplication Agent ──► Compares against existing tasks in MongoDB
       ├── 4. Prioritization Agent ──► Assigns/validates priority based on deadline & workload
       ├── 5. Execution Node      ──► Performs DB operations (create/update/delete/query)
       └── 6. Summary Agent       ──► Produces natural-language reply + follow-up suggestions
       │
       ▼
[MongoDB Atlas] ──► User-isolated task storage
       │
       ▼ (optional)
[Pinecone] ──► Semantic search for dedup + future vault feature
```

---

## Features

- **Voice or text input** — speak or type; voice is always transcribed first so you can review before sending
- **Multi-agent reasoning** — five LangGraph stages turn free-form speech into structured, deduplicated, prioritized tasks
- **Smart date resolution** — "this Friday", "end of month", "in 3 days" resolved against current date via parsedatetime (no LLM hallucination)
- **Web-enriched descriptions** — decomposition agent optionally searches DuckDuckGo to add preparation tips to task descriptions
- **Deduplication** — prevents duplicate tasks; merges if a new deadline is provided for an existing task
- **Priority balancing** — considers deadline proximity and overall workload, not just urgency keywords
- **Dashboard** — tasks grouped by priority, category, or deadline; inline edit/complete/delete
- **Demo tab** — exposes per-agent reasoning so you can see exactly how the pipeline thought
- **Dark / light mode** — smooth theme switching, persists across pages
- **Docker ready** — single `docker compose up --build` to run both services

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit 1.38+, requests, pydub |
| Backend | FastAPI 0.115+, Uvicorn, Pydantic v2 |
| Database | MongoDB Atlas (Motor async driver) |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Speech-to-text | OpenAI Whisper (`whisper-1`) |
| LLM | OpenAI GPT-4o-mini (temperature=0) |
| Orchestration | LangGraph 0.2+, LangChain 0.3+ |
| Date parsing | parsedatetime |
| Web search | DuckDuckGo (ddgs) |
| Vector store | Pinecone (optional, not yet integrated) |
| Containers | Docker + Docker Compose |
| Cloud | GCP Cloud Run (backend) + Streamlit Cloud (frontend) |

---

## Project Structure

```
thought2do/
├── backend/
│   ├── app/
│   │   ├── agents/             # LangGraph nodes + tools + graph assembly
│   │   │   ├── graph.py        # StateGraph, execute_node, process_voice_input()
│   │   │   ├── intent_agent.py
│   │   │   ├── decomposition_agent.py
│   │   │   ├── dedup_agent.py
│   │   │   ├── prioritization_agent.py
│   │   │   ├── summary_agent.py
│   │   │   ├── tools.py        # resolve_date(), web_search()
│   │   │   └── state.py        # AgentState TypedDict
│   │   ├── prompts/            # System prompts for each agent
│   │   ├── routers/            # HTTP routes: auth, tasks, voice
│   │   ├── services/           # Business logic: auth, task, voice, vector
│   │   ├── models/             # Pydantic schemas (Task, User)
│   │   ├── config.py           # pydantic-settings, env loading
│   │   ├── dependencies.py     # DB connection, JWT auth dependency
│   │   └── main.py             # FastAPI entry point, CORS, router registration
│   ├── tests/
│   │   ├── conftest.py         # Fixtures: test_db, test_client, auth_token
│   │   ├── test_agents.py
│   │   ├── test_tasks.py
│   │   ├── test_voice.py
│   │   └── evaluation.py       # Standalone eval harness (20 labeled cases)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── pages/
│   │   ├── 1_Dashboard.py      # Task list: by priority / category / deadline
│   │   ├── 2_Assistant.py      # Chat + voice interface
│   │   ├── 3_Demo.py           # Pipeline transparency view
│   │   └── 4_Settings.py       # Profile, theme, export, defaults
│   ├── components/
│   │   ├── task_card.py        # Priority-bordered expandable cards
│   │   ├── sidebar.py          # Filters, stats, theme toggle, logout
│   │   ├── voice_recorder.py   # st.audio_input wrapper
│   │   └── auth_forms.py       # Login + register forms
│   ├── utils/
│   │   ├── api_client.py       # APIClient (all backend endpoints)
│   │   ├── theme.py            # Dark/light palettes + CSS generator
│   │   └── page.py             # Auth gate + theme injection
│   ├── app.py                  # Streamlit entry point, landing page
│   ├── requirements.txt
│   └── Dockerfile
├── .env.example
├── .dockerignore
├── docker-compose.yml
├── Makefile
├── PLAN.md                     # Canonical build plan and architecture reference
├── DOCUMENTATION.md            # Technical report (architecture, metrics, ethics)
└── README.md                   # This file
```

---

## Local Development Setup

**Prerequisites:** Python 3.10+, a MongoDB Atlas cluster, an OpenAI API key. Pinecone is optional.

```bash
# 1. Clone the repository
git clone <your-repo-url> thought2do
cd thought2do

# 2. Copy the env template and fill in your values
cp .env.example .env
# Edit .env — required keys: OPENAI_API_KEY, MONGODB_URI, JWT_SECRET_KEY

# 3. Install all dependencies
make install

# 4. Start the backend (terminal 1)
make run-backend
# → FastAPI running at http://localhost:8000
# → Docs at http://localhost:8000/docs

# 5. Start the frontend (terminal 2)
make run-frontend
# → Streamlit running at http://localhost:8501
```

### Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | OpenAI key for Whisper + GPT-4o-mini |
| `MONGODB_URI` | Yes | MongoDB Atlas connection string |
| `MONGODB_DB_NAME` | No | Database name (default: `thought2do`) |
| `JWT_SECRET_KEY` | Yes | Random 64-char secret for token signing |
| `JWT_ALGORITHM` | No | JWT algorithm (default: `HS256`) |
| `JWT_EXPIRATION_MINUTES` | No | Token lifetime (default: `1440` = 24 h) |
| `PINECONE_API_KEY` | No | Pinecone key — app works without it |
| `PINECONE_INDEX_NAME` | No | Pinecone index name |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated extra CORS origins (e.g. Streamlit Cloud URL) |

### Makefile Targets

| Target | Purpose |
|---|---|
| `make install` | Install backend + frontend dependencies |
| `make run-backend` | Start FastAPI with hot-reload on :8000 |
| `make run-frontend` | Start Streamlit on :8501 |
| `make test` | Run the pytest suite |
| `make evaluate` | Run the standalone agent evaluation harness |
| `make docker-build` | Build both Docker images |
| `make docker-up` | Start both containers via Docker Compose |
| `make docker-down` | Stop and remove containers |

---

## Docker Setup

Docker Compose bundles both services. MongoDB Atlas stays external (cloud-hosted) — only the app services are containerised.

```bash
# 1. Fill in .env with real values (same file as local dev)
cp .env.example .env

# 2. Build images and start
docker compose up --build

# Backend  →  http://localhost:8000
# Frontend →  http://localhost:8501
```

```bash
# Stop
docker compose down
```

The frontend container automatically receives `BACKEND_URL=http://backend:8000`, routing requests through Docker's internal network rather than localhost.

---

## Deployment

### Backend — GCP Cloud Run

The backend runs as a Docker container on GCP Cloud Run. MongoDB Atlas is used as-is (external cloud database — no containerisation needed).

#### Step 1 — Prerequisites

- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated
- Docker Desktop running
- GCP project created with billing enabled

#### Step 2 — Enable required GCP APIs

```bash
gcloud config set project YOUR_PROJECT_ID

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

#### Step 3 — Allow Cloud Run to reach MongoDB Atlas

Cloud Run uses dynamic egress IPs, so the simplest Atlas config is:

1. MongoDB Atlas → **Network Access** → **Add IP Address**
2. Click **Allow Access from Anywhere** (`0.0.0.0/0`)
3. Confirm

#### Step 4 — Create Artifact Registry repository

```bash
gcloud artifacts repositories create thought2do \
  --repository-format=docker \
  --location=us-central1

gcloud auth configure-docker us-central1-docker.pkg.dev
```

#### Step 5 — Build and push the backend image

Run from the project root (`thought2do/`):

```bash
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT_ID/thought2do/backend:latest ./backend

docker push us-central1-docker.pkg.dev/YOUR_PROJECT_ID/thought2do/backend:latest
```

#### Step 6 — Deploy to Cloud Run

```bash
gcloud run deploy thought2do-backend \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/thought2do/backend:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --set-env-vars "OPENAI_API_KEY=sk-...,MONGODB_URI=mongodb+srv://...,MONGODB_DB_NAME=thought2do,JWT_SECRET_KEY=<64-char-secret>,CORS_ALLOWED_ORIGINS=https://your-app.streamlit.app"
```

Cloud Run prints a **Service URL** on success:

```
Service URL: https://thought2do-backend-abc123-uc.a.run.app
```

Save this URL — you need it for the frontend secrets.

#### Step 7 — (Recommended) Use Secret Manager for sensitive values

```bash
# Store secrets
echo -n "sk-..." | gcloud secrets create OPENAI_API_KEY --data-file=-
echo -n "mongodb+srv://..." | gcloud secrets create MONGODB_URI --data-file=-
echo -n "<jwt-secret>" | gcloud secrets create JWT_SECRET_KEY --data-file=-

# Grant the default compute service account access
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
for SECRET in OPENAI_API_KEY MONGODB_URI JWT_SECRET_KEY; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done

# Redeploy referencing secrets
gcloud run deploy thought2do-backend \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/thought2do/backend:latest \
  --platform managed --region us-central1 --allow-unauthenticated --port 8000 \
  --update-secrets "OPENAI_API_KEY=OPENAI_API_KEY:latest,MONGODB_URI=MONGODB_URI:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest" \
  --set-env-vars "MONGODB_DB_NAME=thought2do,CORS_ALLOWED_ORIGINS=https://your-app.streamlit.app"
```

#### Step 8 — Verify the deployment

```bash
curl https://thought2do-backend-abc123-uc.a.run.app/
# → {"status":"ok","message":"Thought2Do API is running"}
```

#### Redeploying after code changes

```bash
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT_ID/thought2do/backend:latest ./backend
docker push us-central1-docker.pkg.dev/YOUR_PROJECT_ID/thought2do/backend:latest
gcloud run deploy thought2do-backend \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/thought2do/backend:latest \
  --region us-central1
```

---

### Frontend — Streamlit Cloud

The frontend is deployed on [Streamlit Cloud](https://streamlit.io/cloud) directly from the GitHub repository.

#### Step 1 — Push to GitHub

```bash
git add .
git commit -m "ready for deployment"
git push origin main
```

#### Step 2 — Connect on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **New app**
3. Select your repository and branch
4. Set **Main file path** to `frontend/app.py`
5. Click **Advanced settings**

#### Step 3 — Add secrets

In **Advanced settings → Secrets**, add:

```toml
BACKEND_URL = "https://thought2do-backend-abc123-uc.a.run.app"
```

Replace the URL with your Cloud Run service URL from Step 6 above.

#### Step 4 — Deploy

Click **Deploy**. Streamlit Cloud installs `frontend/requirements.txt` automatically and starts the app.

Once deployed, copy the public URL (e.g. `https://your-app.streamlit.app`) and go back to your Cloud Run service to add it to `CORS_ALLOWED_ORIGINS`.

---

## API Reference

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/auth/register` | No | Register a new user |
| POST | `/auth/login` | No | Login, returns JWT |
| GET | `/auth/me` | Yes | Get current user profile |
| GET | `/tasks` | Yes | List tasks (filterable by status, category, priority) |
| POST | `/tasks` | Yes | Create a task manually |
| GET | `/tasks/{id}` | Yes | Get a single task |
| PUT | `/tasks/{id}` | Yes | Update a task |
| DELETE | `/tasks/{id}` | Yes | Delete a task |
| POST | `/voice/transcribe` | Yes | Upload audio → Whisper transcript |
| POST | `/voice/process` | Yes | Audio or text → full agent pipeline |

Interactive docs available at `http://localhost:8000/docs` when running locally.

---

## Testing & Evaluation

```bash
# Run the pytest suite
make test

# Run the standalone evaluation harness (real LLM calls, 20 labeled cases)
make evaluate
# → Prints intent/category/priority/deadline/dedup accuracy
# → Saves results to backend/tests/eval_results.json
```

---

## Documentation

See [Project_Documentation.md](Project_Documentation.md) for the full technical report covering:

- Detailed system architecture diagrams
- Implementation deep-dives (LangGraph routing, tool-calling, MongoDB aggregation, JWT auth)
- Performance metrics (latency, token costs, evaluation scores)
- Challenges and solutions
- Future improvements
- Ethical considerations

---

*Thought2Do — Voice-Driven Agentic Task Management*
*Built by **Yohan Markose** | Northeastern University | Prompt & Agentic AI | Spring 2026*
