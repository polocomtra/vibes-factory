# Repository Guidelines

## Project Structure & Architecture

VibesFactory is a production-inspired agent platform with a modular-monolith API and a Next.js console. Backend code lives in `apps/api/app/`; each capability (for example, `agents/`, `runtime/`, `tools/`, or `mcp/`) keeps its routes, schemas, services, and contracts together. The web application is in `apps/web/src/app/` and reusable UI lives in `apps/web/src/components/`. Database models are in `apps/api/app/models.py`; Alembic migrations are in `migrations/versions/`. Unit tests live in `tests/unit/`, and product specifications and ADRs live in `docs/`.

Preserve domain boundaries: workspace IDs enforce tenant isolation; published agent and tool versions are immutable; runtime/provider/tool contracts must not expose vendor SDK types.

## Build and Run the Application

Run the complete application through Docker Compose from the repository root.
Do not start a second host copy of the API, worker, web app, or database while
using the Compose stack. A local Docker installation with Compose v2 is the
only application runtime prerequisite; Python and Node.js are not needed to
run the app.

1. Create local configuration:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and replace the example values. At minimum, configure:

   - `POSTGRES_PASSWORD` with a non-empty local database password.
   - `VF_ENCRYPTION_MASTER_KEY` with a URL-safe base64 key representing 32
     random bytes. Generate one with
     `openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'`.
   - Supabase Auth settings: `VF_SUPABASE_URL`,
     `VF_SUPABASE_PUBLISHABLE_KEY`, and `VF_SUPABASE_JWT_JWKS_URL`.
   - A model provider credential and endpoint. The default agent model uses
     Azure OpenAI, so set `VF_AZURE_OPENAI_API_KEY`,
     `VF_AZURE_OPENAI_BASE_URL`, and `VF_AZURE_OPENAI_DEPLOYMENT_NAME` to a
     deployment available to you. Alternatively, configure another supported
     provider in the application.

3. Build images and start the stack:

   ```bash
   docker compose up -d --build
   docker compose ps
   ```

   Compose starts the web console, API, PostgreSQL with pgvector, embedding
   service, and async worker. The one-shot `migrate` service applies Alembic
   migrations before the API and worker start. The first build can take a few
   minutes because it builds the embedding image and downloads its pinned
   model. Wait for the API and embedding services to become healthy; the worker
   should show `Up` in `docker compose ps`.

4. Open the app and create a research agent:

   - Console: <http://localhost:3000>
   - API docs: <http://localhost:8000/docs>
   - API health/readiness: <http://localhost:8000/health> and
     <http://localhost:8000/ready>

   Sign in through the configured Supabase project. Create an agent from the
   **Deep Research** template, configure its model, ensure `web_search` and
   `fetch_web_resource` are enabled, then publish a version before opening its
   Playground. Async agent runs are enabled by default for the Compose stack
   (`VF_ENABLE_ASYNC_AGENT_RUNS=true`); the worker must remain running to
   process queued research runs.

Useful Compose operations (run from the repository root):

```bash
docker compose logs -f api worker       # follow runtime and background-worker logs
docker compose up -d --build api worker # rebuild/restart backend services after Python changes
docker compose up -d --build web       # rebuild/restart the console after web changes
docker compose down                    # stop services; preserve database and blob volumes
```

Database state and uploaded blobs live in named Docker volumes. `docker compose
down -v` removes those volumes and permanently deletes local database and blob
data; use it only when you intend to reset the local environment. PostgreSQL
is exposed on `127.0.0.1:15432` for optional database tools.

## Tests and Source Checks

The application itself remains in Docker. For source-level checks, install the
development tools on the host or use the API development image. Backend checks
from the repository root:

```bash
python -m pip install -e "./apps/api[dev]"
PYTHONPATH=. pytest -q
ruff check apps/api tests
ruff format --check apps/api tests
mypy apps/api/app
```

For web checks, run from `apps/web`:

```bash
npm run lint
npm run typecheck
npm run build
```

## Coding Style & Testing

Python targets 3.11, uses four-space indentation, 88-character lines, double quotes, and strict MyPy. Run `ruff check apps/api tests` and `ruff format apps/api tests` before submitting backend changes. Keep FastAPI routers thin; put business logic in services and use Pydantic schemas/contracts at boundaries.

Use TypeScript/React components in `PascalCase` and hooks/utilities in `camelCase`. Follow the existing Next.js ESLint configuration and place route pages under `src/app/`.

Name tests `test_<behavior>.py` and functions `test_<expected_behavior>()`. Add focused unit coverage for changed behavior, especially authorization, workspace scoping, immutable versions, error normalization, budgets, and provider/tool adapters. Run `pytest` plus relevant web checks before review.

## Commits, Pull Requests & Configuration

Recent history favors short imperative summaries, e.g. `add mcp servers` and `implement SSE`; use that style and keep each commit narrowly scoped. Pull requests should explain the user-visible or architectural change, note migrations/configuration changes, link the relevant issue or ADR when applicable, and include screenshots for console UI changes.

Never commit `.env`, `.env.local`, credentials, encryption keys, or Supabase service-role secrets. Update `.env.example` and documentation when introducing a required non-secret setting.
