# VibesFactory

## Phase 9 Knowledge Base & RAG

The local stack now includes `api`, `worker`, `embedding`, `web` and
`pgvector` PostgreSQL. Run `alembic upgrade head` before uploading sources.
Knowledge uploads accept PDF, UTF-8 TXT and Markdown, ingest asynchronously,
and expose grounded retrieval with runtime-generated citations. Set
`VF_EMBEDDING_REVISION` to an immutable Hugging Face revision; `main` is not a
valid production setting. See `docs/ADR/ADR-011-postgresql-leased-ingestion-queue.md`.

Production-inspired Agentic AI Platform.

## Local setup

Requirements: Docker, Python 3.11+, Node.js 22+ and npm.

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD and VF_ENCRYPTION_MASTER_KEY in .env before starting.
docker compose up --build
```

Generate a PostgreSQL password with `openssl rand -hex 24`. Generate the
credential-vault key with:

```bash
python3 -c 'import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

The Compose stack reads `.env`, uses the `postgres` service address inside
containers, and binds the PostgreSQL host port to loopback only. For a Compose
deployment on a VM, set `VF_DATABASE_URL_COMPOSE`, `VF_ENVIRONMENT`, and
`VF_CORS_ORIGINS` to the target environment values. For Cloud Run, set
`VF_DATABASE_URL`, `VF_ENVIRONMENT`, and `VF_CORS_ORIGINS` on the API and worker
services. Set `NEXT_PUBLIC_API_URL` to the public API origin at web image build
time; Next.js embeds it in the browser bundle. Store production secrets in the
cloud secret manager, and do not deploy the local PostgreSQL container as a
publicly reachable database.

If running API and worker directly on the host instead of Docker Compose, keep
the embedding service running and wait for model readiness before starting the
worker:

```bash
uvicorn apps.embedding.main:app --reload --port 8100
python -m apps.api.worker
```

Verify `http://127.0.0.1:8100/ready` returns a JSON response with
`"status":"ready"`. The worker
logs the embedding endpoint, batch size, exception type, status code and
duration when an embedding request fails.

The embedding service performs a real inference warm-up before `/ready` returns
`200`. It defaults to `CPUExecutionProvider` because the macOS CoreML ONNX
provider can hang or consume excessive memory for this model. Override
`VF_EMBEDDING_ORT_PROVIDER` only after validating the provider on the target
machine.

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

For the Phase 12/13 durable workflow checks, run the local PostgreSQL and
worker stack before the Python quality gate:

```bash
docker compose up -d --build postgres migrate api worker
PYTHONPATH=. pytest -q
ruff check apps/api tests
mypy apps/api/app
```

The worker persists every workflow node boundary and replays
`workflow_run_events` through authenticated SSE. A worker restart while a node
is active is intentionally fail-closed as `WORKFLOW_RESUME_UNSAFE`; restart
after a committed boundary resumes from the persisted cursor.

### Supabase Auth configuration

Phase 1 uses Supabase Auth for identity while the local Docker PostgreSQL remains the system of record for VibesFactory users and workspaces.

1. Create a Supabase project and enable Email authentication.
2. Set the Auth Site URL to `http://localhost:3000`.
3. Add `http://localhost:3000/auth/callback` to the Auth redirect URL allow list.
4. Copy the Project URL and Publishable key into the Supabase variables in `.env`.

The publishable key is used by the browser. Never commit `.env`, `.env.local`, database passwords, or Supabase secret/service-role keys. The backend validates the bearer token through Supabase Auth and maps its external user ID into the local `users` table.

### Default Azure OpenAI model

The agent creation form uses the backend catalog default `azure_openai / gpt-6-luna`. Configure the backend-only Azure credential in `.env`:

```bash
VF_AZURE_OPENAI_API_KEY=your_azure_openai_api_key
VF_AZURE_OPENAI_BASE_URL=https://your-resource.services.ai.azure.com/openai/v1
VF_AZURE_OPENAI_DEPLOYMENT_NAME=gpt-6-luna
```

The API key is never sent to the browser or stored in AgentDraft/AgentVersion. Agent creation stores only the provider and model configuration; model execution will consume the configured environment credential in the runtime milestone.

### Gemini runtime model

The Gemini provider integration remains available in the backend registry, but
its models are temporarily hidden from the active catalog while only Luna is
enabled. When a Gemini key is available, re-enable the desired catalog entry
and configure its backend-only Google AI Studio key in `.env`:

```bash
VF_GEMINI_API_KEY=your_gemini_api_key
```

Gemini calls use Google's official `google-genai` Python SDK `Interactions` API.
The key is read only by the API process and is never sent to the browser,
persisted in agent configuration, or included in runtime traces. The
authenticated playground now uses the Phase 5 SSE endpoint for the active Azure
OpenAI model; Gemini streaming remains outside the active catalog scope.

Gemini 3.8 Flash requests intentionally omit the legacy `temperature` field;
older agent configurations remain readable and continue to run with the
model's supported defaults.

Reference: [Google AI Studio Gemini API getting started](https://ai.google.dev/gemini-api/docs/get-started).

For local development, PostgreSQL runs in Docker on host port `15432` so it does not conflict with a native PostgreSQL installation. The local API uses `127.0.0.1:15432` by default.
