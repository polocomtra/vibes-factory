# Repository Guidelines

## Project Structure & Architecture

VibesFactory is a production-inspired agent platform with a modular-monolith API and a Next.js console. Backend code lives in `apps/api/app/`; each capability (for example, `agents/`, `runtime/`, `tools/`, or `mcp/`) keeps its routes, schemas, services, and contracts together. The web application is in `apps/web/src/app/` and reusable UI lives in `apps/web/src/components/`. Database models are in `apps/api/app/models.py`; Alembic migrations are in `migrations/versions/`. Unit tests live in `tests/unit/`, and product specifications and ADRs live in `docs/`.

Preserve domain boundaries: workspace IDs enforce tenant isolation; published agent and tool versions are immutable; runtime/provider/tool contracts must not expose vendor SDK types.

## Build, Test, and Development Commands

From the repository root:

```bash
cp .env.example .env              # create local configuration
docker compose up --build         # start web, API, and PostgreSQL
python -m pip install -e "./apps/api[dev]"
alembic upgrade head              # apply database migrations
pytest                            # run the Python test suite
```

For the web app, run commands from `apps/web`:

```bash
npm run dev        # start Next.js locally
npm run lint       # run ESLint and Next.js checks
npm run typecheck  # validate TypeScript without emitting files
npm run build      # create a production build
```

## Coding Style & Testing

Python targets 3.11, uses four-space indentation, 88-character lines, double quotes, and strict MyPy. Run `ruff check apps/api tests` and `ruff format apps/api tests` before submitting backend changes. Keep FastAPI routers thin; put business logic in services and use Pydantic schemas/contracts at boundaries.

Use TypeScript/React components in `PascalCase` and hooks/utilities in `camelCase`. Follow the existing Next.js ESLint configuration and place route pages under `src/app/`.

Name tests `test_<behavior>.py` and functions `test_<expected_behavior>()`. Add focused unit coverage for changed behavior, especially authorization, workspace scoping, immutable versions, error normalization, budgets, and provider/tool adapters. Run `pytest` plus relevant web checks before review.

## Commits, Pull Requests & Configuration

Recent history favors short imperative summaries, e.g. `add mcp servers` and `implement SSE`; use that style and keep each commit narrowly scoped. Pull requests should explain the user-visible or architectural change, note migrations/configuration changes, link the relevant issue or ADR when applicable, and include screenshots for console UI changes.

Never commit `.env`, `.env.local`, credentials, encryption keys, or Supabase service-role secrets. Update `.env.example` and documentation when introducing a required non-secret setting.
