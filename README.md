# WorksheetForge

An AI-powered worksheet generation platform for Olympiad, JEE, and NEET preparation.
Generates premium styled `.docx` worksheets from uploaded PDF/DOCX source files via a
multi-phase Claude AI pipeline.

## Key characteristics

- **Ephemeral documents**: Generated worksheets are stored for **2 hours only**, then
  auto-deleted from both Supabase Storage and the database. Download promptly.
- **Multi-phase AI pipeline**: source audit → skeleton → MCQ generation → solutions → DOCX assembly.
- **Prompt caching**: Claude API calls use `cache_control: ephemeral` on system prompts and
  source text blocks to minimise token costs.
- **Single-user internal tool**: no multi-tenancy complexity; one account, full access.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 App Router, TypeScript, Tailwind CSS, shadcn/ui, TipTap, TanStack Query |
| Backend | FastAPI (Python 3.11), SQLAlchemy 2.0 async, Pydantic v2, Alembic |
| AI | Anthropic Claude (claude-opus-4-5) via `anthropic` SDK |
| Worker | RQ (Redis Queue) |
| Queue / Pub-Sub | Render Redis |
| Database | Supabase Postgres |
| Storage | Supabase Storage (`source-files` + `generated-docs` buckets) |
| Document assembly | Pandoc + texlive-xetex |

## Quick start

### Prerequisites

- Docker + Docker Compose
- A Supabase project with two buckets created: `source-files`, `generated-docs`
- An Anthropic API key

### 1. Clone and configure

```bash
git clone <repo-url>
cd worksheet-generator
```

Copy `.env.example` and fill in your credentials:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql+asyncpg://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
REDIS_URL=redis://localhost:6379
JWT_SECRET=<generate a long random string>
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY=<service role key from Supabase dashboard>
SUPABASE_SOURCE_BUCKET=source-files
SUPABASE_DOCS_BUCKET=generated-docs
CORS_ALLOWED_ORIGINS=http://localhost:3000
DOCUMENT_TTL_HOURS=2
```

### 2. Run the backend

```bash
cd backend
docker-compose up --build
```

This starts:
- **api** on `http://localhost:8000` (FastAPI)
- **worker** — RQ worker processing `worksheet-generation` and `cleanup` queues
- **redis** on port 6379

### 3. Run database migrations

In a new terminal (with backend running):

```bash
docker-compose exec api alembic upgrade head
```

### 4. Run the frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # or create manually
npm run dev
```

Create `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=<same or different random string>
NEXTAUTH_API_URL=http://localhost:8000/api
```

Open `http://localhost:3000`. Register an account and start creating projects.

### 5. Production deployment

- **Backend**: Deploy to Render using the `Dockerfile`. Set all env vars in the Render dashboard.
  Create two services: `api` (web) and `worker` (background worker) from the same Docker image,
  using `CMD` override `rq worker --url $REDIS_URL worksheet-generation cleanup` for the worker.
- **Frontend**: Deploy to Vercel. Set `NEXT_PUBLIC_API_URL` to your Render API URL.
- **Redis**: Use Render Redis add-on; copy the internal Redis URL to `REDIS_URL`.
- **Database**: Supabase Postgres — copy the pooler connection string (Transaction mode) to `DATABASE_URL`.

## Document expiry

Worksheets are **ephemeral**. After generation:

- A 2-hour countdown appears in the editor header and history list.
- The `/api/documents/{id}/download` endpoint returns HTTP 410 Gone after expiry.
- A cleanup RQ job runs every 30 minutes and deletes expired documents from both
  Supabase Storage and the Postgres database.
- Saving a document in the editor resets the TTL to `now + 2 hours`.

## API documentation

The interactive API docs are available at `http://localhost:8000/docs` (Swagger UI)
and `http://localhost:8000/redoc` when the backend is running.
