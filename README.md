# VibesFactory

Production-inspired Agentic AI Platform.

## Local setup

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

### Supabase Auth configuration

Phase 1 uses Supabase Auth for identity while the local Docker PostgreSQL remains the system of record for VibesFactory users and workspaces.

1. Create a Supabase project and enable Email authentication.
2. Set the Auth Site URL to `http://localhost:3000`.
3. Add `http://localhost:3000/auth/callback` to the Auth redirect URL allow list.
4. Copy the Project URL and Publishable key into the Supabase variables in `.env`.

The publishable key is used by the browser. Never commit `.env`, `.env.local`, database passwords, or Supabase secret/service-role keys. The backend validates the bearer token through Supabase Auth and maps its external user ID into the local `users` table.

Agents, model providers, runtime, tools, RAG and workflows are introduced in later milestones.

For local development, PostgreSQL runs in Docker on host port `15432` so it does not conflict with a native PostgreSQL installation. The local API uses `127.0.0.1:15432` by default.
