# VibesFactory

Production-inspired Agentic AI Platform.

## Phase 0 local setup

Requirements: Docker, Python 3.11+, Node.js 22+ and npm.

```bash
cp .env.example .env
docker compose up --build
```

The local services are available at:

- Web: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Readiness: http://localhost:8000/ready

Run the migration from the repository root after PostgreSQL is available:

```bash
python -m pip install -e "./apps/api[dev]"
alembic upgrade head
pytest
```

Phase 0 intentionally contains only the platform foundation. Agents, authentication, model providers, runtime, tools, RAG and workflows are introduced in later milestones.

For local development, PostgreSQL runs in Docker on host port `15432` so it does not conflict with a native PostgreSQL installation. The local API uses `127.0.0.1:15432` by default.
