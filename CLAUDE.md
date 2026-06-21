# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend

```bash
# Run everything (API + worker + Redis)
cd backend && docker compose down && docker compose build --no-cache && docker compose up

# Run migrations (once containers are up)
docker compose exec api alembic upgrade head

# Run API only (outside Docker)
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run Celery worker (outside Docker — Windows compatible)
cd backend && celery -A app.worker.celery_app worker --pool=threads --concurrency=2 -Q worksheet-generation,cleanup --beat --loglevel=info

# Seed initial user (copy into running container first)
docker cp seed.py backend-api-1:/app/seed.py && docker compose exec api python seed.py
```

### Frontend

```bash
cd frontend && npm install
cd frontend && npm run dev      # http://localhost:3000
cd frontend && npm run build
```

### Environment setup

```bash
cp backend/.env.example backend/.env        # fill in keys
cp frontend/.env.local.example frontend/.env.local
```

Required env vars (backend): `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`

Required env vars (frontend): `NEXT_PUBLIC_API_URL`, `NEXTAUTH_URL`, `NEXTAUTH_SECRET`

---

## Architecture

Four-tier stack:

```
Next.js 14 (Vercel)
    ↓ REST + SSE  (Bearer JWT from NextAuth)
FastAPI backend (Render, port 8000)  ←→  Supabase Postgres (async SQLAlchemy + psycopg3)
    ↓ RQ enqueue
RQ Worker (Render Background Worker)  ←→  Render Redis (job queue + pub/sub)
    ↓
Claude API / Gemini API  +  Supabase Storage
```

**Supabase** serves two roles:
- **Postgres**: all domain data (users, projects, files, runs, documents, chat)
- **Storage**: two buckets — `source-files` (uploaded PDFs/DOCXs), `generated-docs` (output DOCX files)

**Redis** serves two roles:
- RQ job queue (queue names: `worksheet-generation`, `cleanup`)
- SSE pub/sub channel per run: `run:{run_id}:progress`

**Database driver**: `psycopg3` (not asyncpg). asyncpg breaks with Supabase Supavisor pooler on Docker/Windows due to SSL/SNI issues. `database.py` auto-converts `postgresql+asyncpg://` URLs to `postgresql+psycopg://`.

---

## Generation pipeline

A "Generate Worksheet" click goes through 8 phases:

```
Phase 1: source_audit               → Claude reads source, identifies topics/difficulty/formulas
Phase 2: worksheet_skeleton         → Claude plans all sections + exact question counts
Phase 3: generate_section_1_mcq     → Single-correct MCQ questions + solutions (1 call)
Phase 4: generate_section_2_multi   → Multiple-correct MCQ questions + solutions (1 call)
Phase 5: generate_section_3_areason → Assertion-Reason questions + solutions (1 call)
Phase 6: generate_section_4_integer → Integer/Numerical type questions + solutions (1 call)
Phase 7: generate_section_5_passage → Passage-based comprehension + solutions (1 call)
Phase 8: assemble_docx              → No AI call — splits questions/solutions, joins all sections
```

Each section phase (3–7) outputs strictly:
```
## QUESTIONS
Q1. ...
## SOLUTIONS
**Q1.** Answer: (B) — explanation...
```

`assemble_docx` collects all sections, splits on those markers, and builds:
```
[skeleton header]
[Section 1 questions] ... [Section 5 questions]
---
ANSWER KEY
[Section 1 solutions] ... [Section 5 solutions]
```

**Why per-section:** Each call stays within ~8192 output tokens. Supports 40–100 total questions without truncation. Failed sections can be retried independently.

**Pandoc invocation** (`services/pandoc.py`): `pandoc input.md --from markdown+tex_math_dollars --to docx --reference-doc reference.docx -o output.docx`.

**Prompt caching** (`providers/anthropic_provider.py`): every Claude call marks the system message block and the source-text user block with `"cache_control": {"type": "ephemeral"}`. Cuts costs significantly on repeat calls since source text is cached across all phases.

---

## LLM Provider system

Provider is selected per-run via the Generate UI (or falls back to `LLM_PROVIDER` env var).

```
services/generation/providers/
├── base.py              — LLMProvider abstract class, CompletionResult dataclass
├── anthropic_provider.py — Claude with prompt caching, per-model pricing
├── gemini_provider.py   — Gemini streaming, usage metadata
└── factory.py           — reads LLM_PROVIDER + model override, returns provider
```

To switch default provider: set `LLM_PROVIDER=anthropic` or `LLM_PROVIDER=gemini` in `.env`.

Per-run override: the Generate UI shows a provider/model selector. Selection is stored on `runs.llm_provider` + `runs.llm_model` columns.

---

## 2-hour document expiry

Generated documents are ephemeral. The TTL is enforced at every layer:

| Layer | Behaviour |
|---|---|
| **DB** | `documents.expires_at` column; set to `now + 2h` on creation; reset to `now + 2h` on every editor save |
| **API** | `GET /documents/{id}/download` and `POST /documents/{id}/save` both return **HTTP 410 Gone** if `expires_at < now` |
| **Supabase signed URLs** | Generated with a 2-hour expiry, aligned with document TTL |
| **Cleanup job** | `services/cleanup.py` → RQ task `run_cleanup` runs every 30 min; deletes Supabase Storage objects for all versions, then cascades-deletes DB rows |
| **Frontend editor** | `DocEditor` counts down live; banner turns amber below 30 min, red on expiry; download + save buttons disabled when expired |

`DOCUMENT_TTL_HOURS` env var controls the TTL (default `2`).

---

## Key non-obvious patterns

**SSE streaming**: Backend publishes JSON events to Redis channel `run:{run_id}:progress`. The `GET /runs/{id}/stream` endpoint subscribes and re-streams as `text/event-stream`. Frontend `PhaseProgress` opens a native `EventSource` with `?token=JWT` (EventSource cannot send headers). Closes on terminal events (`run_completed` / `run_failed`).

**Async + executor**: Phase functions call the LLM API with streaming — they run in `loop.run_in_executor(None, phase_fn)` to avoid blocking the async event loop. DB operations stay async throughout.

**Document versioning**: `Document.current_version` increments on each editor save. All versions kept in Supabase at `{doc_id}/v{N}.docx`. Cleanup deletes every version when the document expires.

**Editor round-trip**: TipTap (HTML) → `services/editor.py` (HTML→markdown) → Pandoc (markdown+LaTeX→DOCX) → Supabase. Reverse: Supabase DOCX → `GET /documents/{id}/content` → mammoth (DOCX→HTML) → TipTap.

**File extraction on upload**: `services/extraction.py` runs immediately when a source file is uploaded; `ProjectFile.extracted_text` is stored in Postgres so the orchestrator can access it without re-fetching the file from Supabase at generation time.

---

## Model

Claude model used for Anthropic: `claude-opus-4-5` (default). Change via `ANTHROPIC_MODEL` env var or per-run in the UI.
Gemini model: `gemini-2.0-flash` (default). Change via `GEMINI_MODEL` env var or per-run in the UI.
