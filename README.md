# Story Continuation App — Project Document

An AI application that takes incomplete books and stories, proposes several directions the plot could go, and writes the continuation the user picks. Users can rewind and explore alternate branches.

This document is the single reference for the project: what it does, how it's built, why each decision was made, the code written so far, and the problems already solved during setup.

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Architecture](#2-architecture)
3. [Architectural Decisions](#3-architectural-decisions)
4. [Data Model](#4-data-model)
5. [The AI Pipeline](#5-the-ai-pipeline)
6. [Prompt Templates](#6-prompt-templates)
7. [Backend (FastAPI)](#7-backend-fastapi)
8. [Frontend (Next.js)](#8-frontend-nextjs)
9. [Database Setup (Postgres + pgAdmin)](#9-database-setup-postgres--pgadmin)
10. [Running Locally](#10-running-locally)
11. [Deployment](#11-deployment)
12. [Build Roadmap](#12-build-roadmap)
13. [Risks and Mitigations](#13-risks-and-mitigations)
14. [Troubleshooting Log](#14-troubleshooting-log)

---

## 1. Product Overview

### The user loop

1. User uploads or pastes an incomplete story (TXT, EPUB, PDF, or plain text).
2. The app analyzes it and builds a structured understanding of the story.
3. The AI proposes 3 distinct directions the plot could take next.
4. User picks one.
5. The AI writes the continuation, streamed to the screen.
6. Repeat from step 3. At any point the user can rewind to an earlier point and choose a different branch.

### The core technical problem

A novel is 100k+ words (~150k tokens). Resending the entire book on every generation is slow, expensive, and degrades quality. The central engineering problem is **context management**: maintaining a compact, accurate representation of the story that stays correct as the story grows. Everything in the AI pipeline exists to solve this.

---

## 2. Architecture

```
┌──────────────────────┐        HTTP/JSON         ┌───────────────────────────┐
│   Next.js frontend   │ ───────────────────────▶ │     FastAPI backend       │
│   (React, Tailwind)  │ ◀─────── streaming ───── │                           │
│                      │                          │  routers/  → HTTP layer   │
│  - upload UI         │                          │  services/ → AI + ingest  │
│  - branch picker     │                          │  models    → SQLModel     │
│  - story reader      │                          └──────┬──────────────┬─────┘
└──────────────────────┘                                 │              │
                                                         ▼              ▼
                                               ┌──────────────┐  ┌──────────────┐
                                               │  PostgreSQL  │  │  LLM API     │
                                               │  (JSONB,     │  │  (Gemini /   │
                                               │  pgvector)   │  │  Claude /    │
                                               └──────────────┘  │  OpenAI)     │
                                                                 └──────────────┘
```

### Repository layout

```
story-app/
├── frontend/                 ← Next.js (App Router, TypeScript, Tailwind)
│   ├── app/
│   ├── lib/api.ts
│   └── .env.local
└── backend/                  ← FastAPI
    ├── app/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── config.py
    │   ├── db.py
    │   ├── models.py
    │   ├── routers/
    │   │   ├── __init__.py
    │   │   ├── stories.py
    │   │   └── nodes.py
    │   └── services/
    │       ├── __init__.py
    │       ├── ai_client.py
    │       └── ingest.py
    ├── migrations/           ← Alembic
    ├── .env
    ├── requirements.txt
    └── venv/                 ← not committed
```

One Git repository, two deploy targets, each pointed at its own subdirectory.

### Responsibilities

| Layer | Owns |
|---|---|
| Frontend | UI, upload, branch selection, rendering the streamed continuation, branch-tree navigation |
| Backend routers | HTTP endpoints, request validation |
| Backend services | Document parsing, chunking, all LLM calls, context assembly |
| Database | Stories, the node tree, branch options, story bible snapshots |
| LLM API | Analysis, branch proposals, prose generation |

The frontend never calls the LLM directly. API keys live only on the backend.

---

## 3. Architectural Decisions

Each decision is recorded with the alternatives considered and the reason for the choice.

### 3.1 Stack: Next.js + Python FastAPI (Option B)

**Options considered:**

- **A. Next.js full-stack** — one repo, one deploy, Vercel AI SDK for streaming. Fastest to build. Weakness: long ingest jobs exceed serverless timeouts.
- **B. Next.js frontend + FastAPI backend** — chosen.
- **C. React (Vite) + Node/Express** — most control, most boilerplate.

**Why B:**
- Python has the strongest ecosystem for document parsing (`ebooklib`, `pypdf`), chunking, and embeddings.
- A persistent Python server has no serverless timeout ceiling, so long-running ingest is simpler.
- Demonstrates two languages and a service-oriented architecture — useful as a portfolio project.

**Cost accepted:** two deployments, CORS configuration, and a network hop between frontend and backend.

### 3.2 Database: PostgreSQL over MySQL

**Why Postgres:**
1. **JSONB.** The story bible is the app's most important data structure and is document-shaped. Postgres JSONB supports querying inside JSON and indexing those queries. MySQL's JSON type is weaker here.
2. **pgvector.** Embedding-based retrieval of earlier passages is a planned later feature. `pgvector` is a drop-in Postgres extension; choosing MySQL now would mean a migration later.
3. **Hosting.** Neon and Supabase offer strong free Postgres tiers.

**If MySQL were used instead:** swap `psycopg2-binary` for `PyMySQL`, use `mysql+pymysql://` URLs, and change JSONB columns to JSON.

### 3.3 Context strategy: bible + rolling summary + verbatim tail

Instead of sending the whole book, every generation receives:

| Component | Size | Purpose |
|---|---|---|
| Story bible (JSON) | ~1–2k tokens | Facts, characters, threads — what must stay consistent |
| Rolling summary (prose) | ~300 words | Narrative momentum — what's been building |
| Last 2,000–4,000 words verbatim | ~3–5k tokens | Voice and immediate continuity |
| Retrieved passages (later) | variable | Specific earlier details the bible references |

This reduces each call from ~150k tokens to ~8k.

### 3.4 Incremental updates instead of re-analysis

After each accepted continuation, the bible and summary are **updated** with only the new passage, not rebuilt from the whole story. Cost stays roughly constant regardless of story length.

### 3.5 Branch tree from day one

Every generated passage is a **node** with a `parent_id`. This makes rewind-and-retry and alternate branches possible without a schema change. Even if v1 shows a linear view, the schema supports the tree.

### 3.6 Forced diversity in branch options

Branch options are required to use different **approach types** (ESCALATE, REVEAL, QUIET, REVERSAL). Without this constraint, models return three variations of the same idea.

### 3.7 Separate calls for separate jobs

Four different LLM calls (analysis, update, branch proposal, prose) rather than one mega-prompt. Each can use a different model, temperature, and output format; the cheap structured calls use JSON mode, the expensive prose call streams.

### 3.8 Model-agnostic adapter

All LLM calls go through one function (`call_model`). Swapping Gemini, Claude, or OpenAI is a one-file change, which also allows side-by-side benchmarking of continuation quality.

**Model notes:** Gemini's large context window is forgiving early on. Claude tends to be strongest at sustained prose voice. GPT is reliable at structured JSON.

### 3.9 Pinned dependencies

`requirements.txt` pins exact versions and everything is installed in one command. This was adopted after unpinned, one-at-a-time installs caused pip resolver failures (see [Troubleshooting](#14-troubleshooting-log)).

### 3.10 Migrations from the start

Alembic is set up before the first table exists, so schema changes never require dropping the dev database.

### 3.11 Background jobs: deferred

Start with synchronous ingest. Move to FastAPI `BackgroundTasks` when waiting becomes annoying, then to a real queue (Celery + Redis, or Inngest) when retries, job status, or surviving restarts are needed.

---

## 4. Data Model

### Tables

```
stories
  id              UUID  PK
  user_id         TEXT
  title           TEXT
  original_text   TEXT
  bible_json      JSONB
  created_at      TIMESTAMP

nodes
  id              UUID  PK
  story_id        UUID  FK → stories.id
  parent_id       UUID  FK → nodes.id   (NULL = first node after the original)
  content         TEXT
  bible_snapshot  JSONB                 (bible state after this node)
  rolling_summary TEXT                  (summary state after this node)
  created_at      TIMESTAMP

options
  id              UUID  PK
  node_id         UUID  FK → nodes.id   (the node these options follow)
  approach_type   TEXT
  title           TEXT
  pitch           TEXT
  was_chosen      BOOLEAN
```

### Why snapshots live on nodes

Storing the bible and summary **per node** means rewinding to any node restores the exact story state at that point. Branching from an earlier node never sees facts that only exist on a different branch.

### Reconstructing a branch

To display the full text of a branch, walk `parent_id` from the current node back to the root and concatenate `content` in order, prefixed by `stories.original_text`. In Postgres this can be one recursive CTE:

```sql
WITH RECURSIVE path AS (
  SELECT id, parent_id, content, created_at FROM nodes WHERE id = :node_id
  UNION ALL
  SELECT n.id, n.parent_id, n.content, n.created_at
  FROM nodes n JOIN path p ON n.id = p.parent_id
)
SELECT content FROM path ORDER BY created_at;
```

---

## 5. The AI Pipeline

```
 upload ──▶ [1] Bible Extraction (once; map-reduce for long books)
                     │
                     ▼
            ┌──▶ [2] Context Assembly (bible + summary + last N words)
            │         │
            │         ▼
            │    [3] Branch Options (JSON, cheap)
            │         │
            │     user picks one
            │         │
            │         ▼
            │    [4] Continuation (streamed, expensive)
            │         │
            │         ▼
            │    [5] Bible Update + Rolling Summary Update (cheap)
            │         │
            └─────────┘
```

### Stage 1 — Ingest and analyze (once per upload)

- Parse the file to plain text.
- Chunk by chapter or scene (~3–5k words per chunk).
- Run bible extraction on the first chunk; for each subsequent chunk, run the bible update template against the growing bible. This is map-reduce over the book.
- Estimated cost: roughly $0.10–$1 per book depending on model.

### Stage 2 — Context assembly (before every generation)

```python
def assemble_context(node) -> dict:
    return {
        "bible": node.bible_snapshot,
        "summary": node.rolling_summary,
        "recent_text": last_n_words(full_branch_text(node), 2000),
    }
```

Mark the bible block as cacheable if the provider supports prompt caching (Anthropic and Gemini both do). It's resent on every call but changes only once per cycle.

### Stage 3 — Branch options

Cheap, JSON-mode call. Returns exactly N options with distinct approach types.

### Stage 4 — Continuation

Expensive, streamed call. Stream tokens to the frontend so the user sees text immediately — this is the only user-facing latency in the loop.

Generate in scene-sized pieces (~800–1,200 words). Models ignore word-count targets on longer requests.

### Stage 5 — State update

Run the bible update and rolling summary templates on the new passage. Save both onto the new node.

**Trust feature:** since the bible update returns the complete bible, diff old vs. new and show the user what changed. This lets users correct hallucinated facts before they propagate.

---

## 6. Prompt Templates

Variables are `{{like_this}}`. Templates 1, 2, and 4 use JSON mode.

### 6.1 Story Bible Extraction

**System:**
```
You are a literary analyst building a structured reference document for a
ghostwriter who will continue this story. Extract only what is stated or
strongly implied by the text — do not invent details. Output valid JSON
matching the schema exactly. No prose outside the JSON.
```

**User:**
```
Analyze the following story excerpt and extract a story bible.

<story_text>
{{chunk_text}}
</story_text>

Return JSON with this exact shape:

{
  "pov": "string — narrative POV and tense, e.g. 'third limited, past tense'",
  "voice_notes": "string — 2-4 sentences on prose style: sentence length,
    dialogue density, formality, recurring devices",
  "characters": [
    {
      "name": "string",
      "role": "protagonist | antagonist | supporting | minor",
      "traits": ["string"],
      "current_state": "string — what they know/want/feel as of the last
        scene in this excerpt",
      "relationships": [{"to": "character name", "nature": "string"}]
    }
  ],
  "setting": {
    "time_period": "string",
    "locations": ["string"]
  },
  "established_facts": ["string — concrete facts the continuation must not
    contradict, e.g. 'Mara is left-handed', 'it is currently winter'"],
  "open_threads": ["string — unresolved questions or planted setups the
    reader will expect addressed"],
  "last_scene_summary": "string — 3-5 sentences on exactly where the text
    leaves off, ending mid-action if it does"
}
```

### 6.2 Bible Update (incremental merge)

**System:**
```
You maintain a story bible for an ongoing narrative. You will be given the
current bible and a newly written passage. Update the bible to reflect the
new passage: add new characters/facts, update character states, close
resolved threads, add new open threads. Preserve everything still accurate.
Output the complete updated JSON — not a diff.
```

**User:**
```
<current_bible>
{{existing_bible_json}}
</current_bible>

<new_passage>
{{newly_generated_text}}
</new_passage>

Return the full updated story bible as JSON, same schema as before.
```

### 6.3 Rolling Summary Update

**System:**
```
You write concise running summaries of an ongoing story for an author's
own reference. Update the summary to incorporate the new passage. Keep it
under {{max_words}} words. Compress older events; keep recent events more
detailed. Write in plain prose, past tense, no headers.
```

**User:**
```
<current_summary>
{{existing_summary}}
</current_summary>

<new_passage>
{{newly_generated_text}}
</new_passage>

Return only the updated summary text.
```

### 6.4 Branch Options

**System:**
```
You are a plot consultant. Given the story so far, propose distinct
directions the narrative could take next. Each option must diverge from
the others in kind, not just detail — vary tone, pacing, and which
character drives the scene. Do not write the scene itself, only pitch it.
Output valid JSON only.
```

**User:**
```
<story_bible>
{{bible_json}}
</story_bible>

<recent_summary>
{{rolling_summary}}
</recent_summary>

<last_2000_words>
{{verbatim_recent_text}}
</last_2000_words>

Propose exactly {{n}} possible directions for what happens next.
Each must use a different one of these approach types, matched to what best
fits the story:
- ESCALATE: raise stakes or introduce immediate conflict
- REVEAL: surface information the reader or a character didn't have
- QUIET: a character/relationship beat with low external action
- REVERSAL: subvert the direction the last passage seemed to set up

Return JSON:
{
  "options": [
    {
      "approach_type": "ESCALATE | REVEAL | QUIET | REVERSAL",
      "title": "string — 3-6 word label for the UI button",
      "pitch": "string — 2-3 sentences, written for the reader choosing,
        not as a scene draft",
      "characters_involved": ["string"],
      "tone_shift": "string — e.g. 'darker', 'unchanged', 'comic relief'"
    }
  ]
}
```

### 6.5 Continuation

**System:**
```
You are ghostwriting a continuation of an existing story. Match the
established voice exactly: {{voice_notes}}. Do not summarize, do not
break the fourth wall, do not add headers or scene labels. Write only the
continuation text, picking up immediately where the excerpt leaves off —
do not repeat or re-narrate the ending of the excerpt.

Hard constraints — do not contradict:
{{established_facts, bulleted}}
```

**User:**
```
<story_bible>
{{bible_json}}
</story_bible>

<recent_summary>
{{rolling_summary}}
</recent_summary>

<last_2000_words_verbatim>
{{verbatim_recent_text}}
</last_2000_words_verbatim>

The reader has chosen this direction for what happens next:
"{{chosen_option.title}}" — {{chosen_option.pitch}}

Write the next {{target_length}} of the story, continuing this direction.
Stay in {{pov}}. End the passage at a natural pause, not mid-sentence.
```

### 6.6 Prompting notes

- **JSON reliability:** use the provider's JSON response mode for 6.1, 6.2, and 6.4. With Claude, prefill the assistant turn with `{`. Always strip code fences before `json.loads`.
- **Facts vs. threads:** `established_facts` are constraints (never contradict). `open_threads` are opportunities (sometimes address, not always).
- **Voice:** `voice_notes` and the verbatim tail matter more for prose quality than the bible's factual fields. Lean on them in 6.5.

---

## 7. Backend (FastAPI)

> The code below includes several fixes over the first draft of the setup guide. They're marked **[fixed]** with the reason.

### 7.1 `requirements.txt`

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlmodel==0.0.22
psycopg2-binary==2.9.10
alembic==1.14.0
python-dotenv==1.0.1
pydantic-settings==2.7.1
pydantic==2.10.4
httpx==0.28.1
```

Install with the venv active:

```powershell
pip install -r requirements.txt
```

### 7.2 `.env`

```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/story_app
AI_API_KEY=your-key-here
FRONTEND_ORIGIN=http://localhost:3000
```

Never commit this file. Add `.env` and `venv/` to `.gitignore`.

### 7.3 `app/config.py`

```python
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

class Settings(BaseSettings):
    database_url: str
    ai_api_key: str = ""
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=ENV_PATH)

settings = Settings()
```

**[fixed]**
- `ENV_PATH` loads `.env` relative to this file, not the current working directory, so the app finds it no matter where `uvicorn` is launched from.
- `model_config = SettingsConfigDict(...)` replaces the Pydantic v1-style inner `class Config`, which is deprecated in Pydantic v2.
- `ai_api_key` defaults to `""` so the server boots before a key exists. Calls that need the key should fail with a clear error.

### 7.4 `app/db.py`

```python
from sqlmodel import create_engine, Session
from app.config import settings

engine = create_engine(settings.database_url, echo=True)

def get_session():
    with Session(engine) as session:
        yield session
```

`echo=True` logs every SQL statement — useful in development, turn off in production.

### 7.5 `app/models.py`

```python
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field


def utcnow():
    return datetime.now(timezone.utc)


class Story(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: str
    title: str
    original_text: str
    bible_json: dict = Field(default_factory=dict, sa_type=JSONB)
    created_at: datetime = Field(default_factory=utcnow)


class Node(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    story_id: uuid.UUID = Field(foreign_key="story.id", index=True)
    parent_id: Optional[uuid.UUID] = Field(default=None, foreign_key="node.id", index=True)
    content: str
    bible_snapshot: dict = Field(default_factory=dict, sa_type=JSONB)
    rolling_summary: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Option(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    node_id: uuid.UUID = Field(foreign_key="node.id", index=True)
    approach_type: str
    title: str
    pitch: str
    was_chosen: bool = False
```

**[fixed]**
- `sa_type=JSONB` now imports the real SQLAlchemy type. The first draft used the string `"JSONB"`, which SQLModel doesn't accept.
- `default_factory=dict` gives new rows an empty bible instead of failing validation.
- `index=True` on foreign keys — tree walks and per-story lookups query these columns constantly.
- `datetime.now(timezone.utc)` replaces the deprecated `datetime.utcnow()`.

### 7.6 Alembic migrations

```powershell
alembic init migrations
```

In `migrations/env.py`:

```python
from sqlmodel import SQLModel
from app.config import settings
from app import models  # noqa: F401 — import so tables register on metadata

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = SQLModel.metadata
```

In `migrations/script.py.mako`, add to the imports so generated migrations can reference SQLModel column types:

```python
import sqlmodel
```

Then:

```powershell
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Verify in pgAdmin that `story`, `node`, `option`, and `alembic_version` tables exist.

### 7.7 `app/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import stories, nodes

app = FastAPI(title="Story Continuation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stories.router, prefix="/stories", tags=["stories"])
app.include_router(nodes.router, prefix="/nodes", tags=["nodes"])


@app.get("/health")
def health():
    return {"status": "ok"}
```

### 7.8 `app/routers/stories.py`

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session
from app.db import get_session
from app.models import Story

router = APIRouter()


class StoryCreate(BaseModel):
    title: str
    original_text: str


@router.post("/")
def create_story(payload: StoryCreate, session: Session = Depends(get_session)):
    story = Story(user_id="temp-user", title=payload.title, original_text=payload.original_text)
    session.add(story)
    session.commit()
    session.refresh(story)
    return story


@router.get("/{story_id}")
def get_story(story_id: uuid.UUID, session: Session = Depends(get_session)):
    story = session.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story
```

**[fixed]** The first draft took `title` and `original_text` as bare function parameters, which FastAPI treats as **query parameters**. The frontend sends a JSON body, so those requests would fail with 422. The `StoryCreate` model makes them a JSON body. Also added a 404.

### 7.9 `app/services/ai_client.py`

```python
import json
import re
import httpx
from app.config import settings


class AIError(Exception):
    pass


async def call_model(system: str, user: str, json_mode: bool = False, max_tokens: int = 2000) -> str:
    """Single entry point for all LLM calls. Returns the model's text output.
    Swap the provider-specific block below to change models."""
    if not settings.ai_api_key:
        raise AIError("AI_API_KEY is not set in .env")

    # --- provider-specific block (example shape; adapt to your provider's API) ---
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://api.your-provider.com/v1/messages",
            headers={"Authorization": f"Bearer {settings.ai_api_key}"},
            json={
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "max_tokens": max_tokens,
            },
        )
    if response.status_code != 200:
        raise AIError(f"Model API error {response.status_code}: {response.text}")
    data = response.json()
    text = extract_text(data)
    # --- end provider-specific block ---

    return text


def extract_text(data: dict) -> str:
    """Pull plain text out of the provider response. Adjust per provider."""
    return "".join(block.get("text", "") for block in data.get("content", []))


def parse_json(text: str) -> dict:
    """Strip code fences and parse. Use for JSON-mode calls."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)
```

**[fixed]** The first draft returned the raw response JSON instead of the model's text, and had no error handling or missing-key check.

### 7.10 `app/services/ingest.py` (skeleton)

```python
from app.services.ai_client import call_model, parse_json
from app.prompts import BIBLE_EXTRACT_SYSTEM, BIBLE_EXTRACT_USER, BIBLE_UPDATE_SYSTEM, BIBLE_UPDATE_USER


def chunk_text(text: str, target_words: int = 4000) -> list[str]:
    """Split on paragraph boundaries into ~target_words chunks."""
    paragraphs = text.split("\n\n")
    chunks, current, count = [], [], 0
    for p in paragraphs:
        words = len(p.split())
        if count + words > target_words and current:
            chunks.append("\n\n".join(current))
            current, count = [], 0
        current.append(p)
        count += words
    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def build_bible(text: str) -> dict:
    """Map-reduce bible extraction across chunks."""
    chunks = chunk_text(text)
    bible = parse_json(await call_model(
        BIBLE_EXTRACT_SYSTEM,
        BIBLE_EXTRACT_USER.format(chunk_text=chunks[0]),
        json_mode=True,
    ))
    for chunk in chunks[1:]:
        bible = parse_json(await call_model(
            BIBLE_UPDATE_SYSTEM,
            BIBLE_UPDATE_USER.format(existing_bible_json=bible, newly_generated_text=chunk),
            json_mode=True,
        ))
    return bible
```

Store the template strings from Section 6 in `app/prompts.py`, using `{name}` placeholders for `str.format`. Remember to escape literal braces in the JSON schemas as `{{` and `}}`.

### 7.11 `app/routers/nodes.py` (outline)

Endpoints to build next:

| Method | Path | Does |
|---|---|---|
| `POST` | `/nodes/{node_id}/options` | Assemble context → branch options call → save `Option` rows → return them |
| `POST` | `/nodes/{node_id}/continue` | Body: `option_id`. Continuation call (streamed) → create child `Node` → run bible + summary updates |
| `GET` | `/nodes/{node_id}/path` | Recursive CTE → full branch text |
| `GET` | `/stories/{story_id}/tree` | All nodes for a story, for rendering the branch tree |

Streaming uses FastAPI's `StreamingResponse` with an async generator that yields text chunks as they arrive from the provider's streaming API.

### 7.12 Background ingest (when needed)

```python
from fastapi import BackgroundTasks

@router.post("/{story_id}/ingest")
def ingest_story(story_id: uuid.UUID, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_ingest_pipeline, story_id)
    return {"status": "processing"}
```

Add an `ingest_status` column to `Story` (`pending | processing | ready | failed`) so the frontend can poll.

---

## 8. Frontend (Next.js)

### 8.1 Create the app

```powershell
cd frontend
npx create-next-app@latest . --tailwind --app --typescript
```

### 8.2 `.env.local`

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 8.3 `lib/api.ts`

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL;

export async function createStory(title: string, text: string) {
  const res = await fetch(`${API_URL}/stories/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, original_text: text }),
  });
  if (!res.ok) throw new Error(`Failed to create story: ${res.status}`);
  return res.json();
}

export async function getOptions(nodeId: string) {
  const res = await fetch(`${API_URL}/nodes/${nodeId}/options`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to get options: ${res.status}`);
  return res.json();
}

export async function streamContinuation(
  nodeId: string,
  optionId: string,
  onChunk: (text: string) => void,
) {
  const res = await fetch(`${API_URL}/nodes/${nodeId}/continue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ option_id: optionId }),
  });
  if (!res.ok || !res.body) throw new Error(`Failed to continue: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}
```

### 8.4 Planned pages

| Route | Purpose |
|---|---|
| `/` | Upload or paste a story |
| `/stories/[id]` | Reader view: current branch text, branch options, streaming continuation |
| `/stories/[id]/tree` | Visual branch tree; click a node to rewind |

---

## 9. Database Setup (Postgres + pgAdmin)

Two supported paths. Either works with the code above; only `DATABASE_URL` changes.

### Path A — Local Postgres + pgAdmin (Windows)

1. Download the EDB installer from postgresql.org/download/windows. It bundles pgAdmin 4.
2. In the wizard: keep all components checked, set a password for the `postgres` superuser, keep port `5432`.
3. Open pgAdmin 4. Set a pgAdmin master password on first launch (separate from the Postgres password).
4. Expand the auto-registered server and enter the `postgres` password.
5. Right-click **Databases → Create → Database**, name it `story_app`.
6. `.env`:
   ```
   DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/story_app
   ```

### Path B — Hosted (Neon or Supabase) + pgAdmin as a client

1. Install pgAdmin alone from pgadmin.org.
2. Copy host, port, database, user, and password from the Neon/Supabase dashboard.
3. In pgAdmin: **Servers → Register → Server**, fill in the Connection tab, set SSL mode to `Require`.
4. Use the provider's connection string as `DATABASE_URL`.

### Connection string anatomy

```
postgresql://USER:PASSWORD@HOST:PORT/DATABASE
             │    │        │    │    └── database name, e.g. story_app
             │    │        │    └─────── usually 5432
             │    │        └──────────── localhost, or the Neon/Supabase host
             │    └───────────────────── URL-encode special characters (@ → %40)
             └────────────────────────── usually postgres locally
```

### Enabling pgvector later

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Neon and Supabase have it available. Local installs may need the extension installed separately.

---

## 10. Running Locally

### First-time backend setup

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
alembic upgrade head
```

### Every session — two terminals

```powershell
# Terminal 1
cd story-app\backend
venv\Scripts\activate
uvicorn app.main:app --reload
```

```powershell
# Terminal 2
cd story-app\frontend
npm run dev
```

- Backend: http://localhost:8000 — Swagger UI at http://localhost:8000/docs
- Frontend: http://localhost:3000

**Check before running uvicorn:** the prompt should start with `(venv)`. If it doesn't, the venv isn't active and the wrong Python will run (see 14.5).

### Testing without the frontend

Use `/docs`. Every endpoint gets a "Try it out" form. Build and verify each backend route here before writing frontend code for it.

---

## 11. Deployment

### Backend → Render (Web Service)

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment variables: `DATABASE_URL`, `AI_API_KEY`, `FRONTEND_ORIGIN`
- Run `alembic upgrade head` as a pre-deploy command or once via Render's shell.

### Frontend → Vercel (or Render)

- Root directory: `frontend`
- Environment variable: `NEXT_PUBLIC_API_URL` = the Render backend URL

### Post-deploy checklist

- [ ] Update backend `FRONTEND_ORIGIN` to the real frontend URL (most common cause of CORS errors after deploy)
- [ ] Production database is hosted (Neon/Supabase), not local
- [ ] `echo=True` turned off in `db.py`
- [ ] `/health` returns `{"status": "ok"}`

---

## 12. Build Roadmap

Build the loop before the infrastructure.

| # | Milestone | Done when |
|---|---|---|
| 1 | Skeleton | `/health` responds, frontend loads, the two talk to each other |
| 2 | Save a story | Textarea in the frontend saves a short story via `POST /stories` |
| 3 | Hardcoded continuation | One prompt, one continuation, raw text on screen |
| 4 | Branch options | User sees 3 options, picks one, gets a continuation |
| 5 | Persistence + tree | Nodes saved; user can leave, come back, and rewind |
| 6 | Bible + context assembly | Works on stories longer than a context window |
| 7 | File upload + background ingest | TXT, EPUB, PDF supported |
| 8 | Polish | Streaming, regenerate, edit generated text, bible diff view, export |
| 9 | Auth + rate limits | Auth.js or Clerk; per-user limits on uploads and generations |
| 10 | Retrieval | pgvector embeddings for earlier-passage lookup |

**Current status:** Milestone 1 in progress — backend dependencies installed, working through configuration errors.

---

## 13. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| **Quality drift** — prose and characters degrade over many generations | Bible anchors facts; bible diff view lets users correct errors; verbatim tail preserves voice |
| **Repetitive branch options** | Forced approach types in the branch prompt |
| **Cost per user** — a full ingest plus many generations adds up | Incremental updates, prompt caching, auth before uploads, rate limits |
| **Long ingest times** | Background jobs, status polling |
| **Ignored length targets** | Generate scene-sized chunks, not chapters |
| **Malformed JSON from the model** | Provider JSON mode, fence stripping, retry once on parse failure |
| **Copyright** | ToS requires users to upload only work they own or public-domain text; demo content from Project Gutenberg |
| **Hallucinated facts propagating across branches** | Per-node bible snapshots isolate branches |

---

## 14. Troubleshooting Log

Problems already hit during setup, their causes, and fixes.

### 14.1 `pydantic-core` fails to build — "Rust not found"

**Symptom:** `pip install fastapi` fails building `pydantic-core` with maturin / "Rust not found".

**Cause:** pip couldn't match a prebuilt wheel and fell back to compiling from source, which needs a Rust toolchain.

**Fix:**
```powershell
python -m pip install --upgrade pip
pip cache purge
pip install -r requirements.txt
```
If still failing, `pip install --only-binary :all: <package>` forces wheels only.

### 14.2 pip backtracks through every uvicorn version, then crashes

**Symptom:** pip downloads dozens of old uvicorn versions, then errors on `uvicorn-0.14.0` with `.* suffix can only be used with == or != operators`.

**Cause:** Installing packages one at a time into a venv with conflicting partial installs. The resolver searched backward for a compatible version and hit an ancient release with metadata modern pip rejects.

**Fix:** delete and recreate the venv, then install everything at once from the pinned `requirements.txt` (Section 7.1). Pinning removes the need for backtracking.

### 14.3 `ModuleNotFoundError: No module named 'app'`

**Cause:** `uvicorn` was run from `story-app/` instead of `story-app/backend/`.

**Fix:** always run from `backend/`. Also confirm `app/__init__.py` exists (can be empty) in `app/`, `app/routers/`, and `app/services/`.

### 14.4 `ValidationError: ai_api_key Field required`

**Cause:** `AI_API_KEY` missing from `.env`, or `.env` not found because pydantic-settings looks in the current working directory by default.

**Fix:** add the key to `backend/.env`, or give the field a default (`ai_api_key: str = ""`). The updated `config.py` in Section 7.3 also loads `.env` by absolute path, so the working directory no longer matters.

### 14.5 Uvicorn running on the wrong Python (3.9 instead of the venv)

**Symptom:** tracebacks show paths like `...\Programming\Python\Python39\lib\site-packages\uvicorn\...`, and the prompt shows `PS C:\...>` without `(venv)`.

**Cause:** the venv wasn't activated in that terminal, so Windows ran a globally installed uvicorn on a system-wide Python 3.9. The venv (Python 3.12) with the pinned packages was never used. This can cause version mismatches that look like unrelated bugs.

**Fix:**
```powershell
cd story-app\backend
venv\Scripts\activate
python --version          # should show the venv's version, not 3.9
where.exe uvicorn         # first result should be inside backend\venv\
uvicorn app.main:app --reload
```
Alternatively, run `python -m uvicorn app.main:app --reload` after activating — `python -m` guarantees the uvicorn belonging to the active Python is used.

If PowerShell refuses to run `activate` with an execution-policy error:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 14.6 Suspicious `DATABASE_URL`

**Symptom:** the validation error showed a connection string ending in `...localhost:5433/localhost`.

**Cause:** the database name segment appears to be `localhost` instead of the real database name, and the port is `5433` rather than the default `5432`.

**Fix:** confirm against pgAdmin — the port is shown under the server's Properties → Connection, and the database name is whatever was created under Databases (e.g. `story_app`). The URL should look like:
```
postgresql://postgres:YOUR_PASSWORD@localhost:5432/story_app
```
Port 5433 is valid if the installer chose it (it does when another Postgres already uses 5432) — just make sure it matches pgAdmin.
