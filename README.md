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

### Default Azure OpenAI model

The agent creation form uses the backend catalog default `azure_openai / gpt-5.6-luna`. Configure the backend-only Azure credential in `.env`:

```bash
VF_AZURE_OPENAI_API_KEY=your_azure_openai_api_key
VF_AZURE_OPENAI_BASE_URL=https://your-resource.services.ai.azure.com/openai/v1
VF_AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.6-luna
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
persisted in agent configuration, or included in runtime traces. Phase 4 uses
the non-streaming async variant; SSE streaming remains deferred to Phase 5.

Gemini 3.8 Flash requests intentionally omit the legacy `temperature` field;
older agent configurations remain readable and continue to run with the
model's supported defaults.

Reference: [Google AI Studio Gemini API getting started](https://ai.google.dev/gemini-api/docs/get-started).

For local development, PostgreSQL runs in Docker on host port `15432` so it does not conflict with a native PostgreSQL installation. The local API uses `127.0.0.1:15432` by default.
