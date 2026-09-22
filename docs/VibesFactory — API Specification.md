# VibesFactory — API Specification

## Phase 9 Knowledge API addendum

KB CRUD, multipart idempotent upload/status/reprocess/delete, debug search,
embedding model discovery and draft binding CRUD are implemented under `/v1`.
Uploads return `202` and never expose physical blob paths. Stable errors cover
unsupported type, size, duplicate, no text, in-progress ingestion, embedding
failure, retrieval failure, workspace mismatch and archived KBs.

Runtime retrieval bindings support `mode: "auto" | "always"` (default
`"auto"`). In auto mode, an agent with the `web_search` tool skips Knowledge
Base retrieval for external-research prompts; explicit document/Knowledge Base
prompts still retrieve. `"always"` forces retrieval for every request.

**Document Version:** 0.1  
**Status:** Proposed / Source of Truth  
**Project:** VibesFactory  
**API Style:** REST + Server-Sent Events  
**Base Version:** `/v1`

Related documents:

- `BRD.md`
- `ARCHITECTURE.md`
- `DATABASE_SCHEMA.md`
- `ERD.md`
- `IMPLEMENTATION_PLAN.md`

---

# 1. Purpose

This document defines the external and internal HTTP API contracts for VibesFactory.

The API supports:

- Authentication context
- Workspaces
- Agents
- Agent drafts and versions
- Sessions
- Runs
- Streaming
- Tools
- Credentials
- MCP
- Knowledge bases
- Documents
- Memory
- Guardrails
- Workflows
- Multi-agent configuration
- Approval requests
- Evaluation
- Deployments
- Public agent invocation
- Monitoring
- Trace inspection
- Audit logs

The API shall follow consistent conventions so that:

```text
Frontend
SDK
CLI
External clients
Coding agents
```

can rely on predictable behavior.

---

# 2. API Design Principles

## 2.1 Resource-Oriented

Prefer:

```text
POST /v1/agents
GET  /v1/agents/{agent_id}
```

over RPC-style endpoints such as:

```text
POST /v1/createAgent
```

Action endpoints are allowed where an operation does not map cleanly to CRUD.

Examples:

```text
POST /v1/agents/{agent_id}/versions

POST /v1/runs/{run_id}/cancel

POST /v1/approval-requests/{id}/approve
```

---

# 3. API Versioning

All stable APIs use:

```text
/v1
```

Example:

```text
GET /v1/agents
```

Breaking changes require a new major API version.

Adding optional fields does not require a new version.

---

# 4. Content Type

Default request and response:

```text
Content-Type: application/json
```

File upload operations may use:

```text
multipart/form-data
```

Streaming uses:

```text
text/event-stream
```

---

# 5. Authentication

Two authentication modes exist.

## 5.1 User Authentication

Used by VibesFactory Web and authenticated developer clients.

Header:

```text
Authorization: Bearer <jwt>
```

JWT is initially issued by Supabase Auth.

Backend resolves JWT into:

```json
{
  "user_id": "uuid",
  "email": "user@example.com"
}
```

The application must never trust identity fields supplied by the request body.

---

# 6. Public Deployment Authentication

Published agent deployments may be invoked using a VibesFactory API key.

Header:

```text
Authorization: Bearer vf_live_xxxxxxxxx
```

or later:

```text
X-VibesFactory-Key: vf_live_xxxxxxxxx
```

MVP should standardize on:

```text
Authorization: Bearer <api-key>
```

to avoid multiple authentication conventions.

---

# 7. Workspace Scoping

Workspace-owned APIs shall explicitly include:

```text
/workspaces/{workspace_id}/...
```

where practical.

Example:

```text
GET /v1/workspaces/{workspace_id}/agents
```

This is preferred over:

```text
GET /v1/agents?workspace_id=...
```

because the tenant boundary becomes explicit.

Resource-by-ID endpoints may still use:

```text
GET /v1/agents/{agent_id}
```

but the backend must resolve and verify workspace access.

---

# 8. Standard HTTP Status Codes

Use:

| Status | Meaning |
|---|---|
| 200 | Successful read/update/action |
| 201 | Resource created |
| 202 | Accepted for async processing |
| 204 | Successful delete/no body |
| 400 | Invalid request |
| 401 | Authentication required/invalid |
| 403 | Authenticated but unauthorized |
| 404 | Resource not found |
| 409 | Resource conflict |
| 422 | Semantic validation failure |
| 429 | Rate limited |
| 500 | Internal platform failure |
| 502 | Upstream provider/tool failure |
| 503 | Temporary service unavailable |
| 504 | Timeout |

Do not return HTTP 200 with an embedded failure object for failed operations.

---

# 9. Error Envelope

All non-stream API errors shall use:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Agent was not found.",
    "request_id": "req_123",
    "details": {}
  }
}
```

Fields:

```text
code
message
request_id
details
```

`details` is optional.

Do not expose:

```text
Python stack traces
SQL statements
provider secrets
raw credentials
internal file paths
```

---

# 10. Standard Error Codes

Initial codes:

```text
AUTHENTICATION_REQUIRED
INVALID_TOKEN
ACCESS_DENIED

RESOURCE_NOT_FOUND
RESOURCE_CONFLICT
RESOURCE_ARCHIVED

VALIDATION_ERROR
INVALID_STATE
IMMUTABLE_RESOURCE

RATE_LIMITED

PROVIDER_ERROR
PROVIDER_RATE_LIMITED
PROVIDER_TIMEOUT

TOOL_EXECUTION_FAILED
TOOL_TIMEOUT
TOOL_ARGUMENT_INVALID
TOOL_BLOCKED

RETRIEVAL_FAILED
DOCUMENT_PROCESSING_FAILED

MEMORY_OPERATION_FAILED

GUARDRAIL_BLOCKED
APPROVAL_REQUIRED

WORKFLOW_FAILED

RUN_FAILED
RUN_CANCELLED
RUN_LIMIT_EXCEEDED

EVALUATION_FAILED

INTERNAL_ERROR
```

---

# 11. Request IDs

Every HTTP request shall have a request ID.

Server returns:

```text
X-Request-ID: <id>
```

If a valid client request ID is supplied:

```text
X-Request-ID
```

the server may reuse it.

Request IDs are not the same as:

```text
run_id
trace_id
```

---

# 12. Timestamps

All timestamps are ISO 8601 UTC.

Example:

```json
{
  "created_at": "2026-09-15T04:30:00Z"
}
```

---

# 13. Pagination

List APIs should support cursor pagination.

Request:

```text
GET /v1/workspaces/{workspace_id}/runs?limit=50&cursor=...
```

Default:

```text
limit = 50
```

Maximum:

```text
limit = 100
```

Response:

```json
{
  "data": [],
  "pagination": {
    "next_cursor": "opaque-value",
    "has_more": true
  }
}
```

Cursor values must be opaque to clients.

---

# 14. List Response Convention

Collection response:

```json
{
  "data": [
    {}
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false
  }
}
```

Do not return raw arrays.

---

# 15. Single Resource Convention

Single-resource endpoints return the resource directly.

Example:

```json
{
  "id": "...",
  "name": "Research Agent"
}
```

Do not unnecessarily wrap:

```json
{
  "data": {
    ...
  }
}
```

for single resources.

---

# 16. Idempotency

Operations that may be retried by clients should support:

```text
Idempotency-Key
```

Initially recommended for:

```text
public deployment run creation

document upload registration

evaluation run creation
```

The same idempotency key with the same authenticated scope should return the previously created resource.

Conflicting payloads with reused keys should return:

```text
409 RESOURCE_CONFLICT
```

---

# 17. Health API

## GET `/health`

Purpose:

Process liveness.

Response:

```json
{
  "status": "ok"
}
```

No authentication required.

---

# 18. Readiness API

## GET `/ready`

Checks critical dependencies.

Response:

```json
{
  "status": "ready",
  "checks": {
    "database": "ok"
  }
}
```

Failure should return:

```text
503
```

---

# 19. Current User API

## GET `/v1/me`

Response:

```json
{
  "id": "uuid",
  "email": "user@example.com",
  "display_name": "William",
  "avatar_url": null
}
```

---

# 20. Workspaces

## POST `/v1/workspaces`

Request:

```json
{
  "name": "Personal",
  "slug": "personal"
}
```

Response `201`:

```json
{
  "id": "uuid",
  "name": "Personal",
  "slug": "personal",
  "role": "OWNER",
  "created_at": "..."
}
```

---

## GET `/v1/workspaces`

Returns workspaces accessible to current user.

---

## GET `/v1/workspaces/{workspace_id}`

Returns workspace details.

---

## PATCH `/v1/workspaces/{workspace_id}`

Owner-only initially.

Request:

```json
{
  "name": "AI Lab"
}
```

---

# 21. Workspace Members

## GET `/v1/workspaces/{workspace_id}/members`

Response item:

```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "role": "MEMBER"
}
```

The MVP returns all members for an authorized workspace member. The owner is listed first.

## POST `/v1/workspaces/{workspace_id}/members`

Owner-only. Adds an existing VibesFactory user by email; invitation email for users who have not signed in is deferred to a later phase.

Request:

```json
{
  "email": "user@example.com"
}
```

Response `201` uses the member response item above. Returns `404 USER_NOT_FOUND_FOR_MEMBERSHIP` when the email is not registered and `409 WORKSPACE_MEMBER_ALREADY_EXISTS` for an existing membership.

## DELETE `/v1/workspaces/{workspace_id}/members/{user_id}`

Owner-only. Removes a non-owner member and returns `204`. The workspace owner cannot be removed.

---

# 22. Agents

## POST `/v1/workspaces/{workspace_id}/agents`

Request:

```json
{
  "name": "Research Agent",
  "slug": "research-agent",
  "description": "Researches technical topics.",
  "instructions": "You are a technical research agent.",
  "model": {
    "provider": "google",
    "name": "gemini-model-name",
    "config": {
      "temperature": 0.2,
      "max_output_tokens": 4096
    }
  }
}
```

Response `201`:

```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "name": "Research Agent",
  "slug": "research-agent",
  "description": "Researches technical topics.",
  "status": "ACTIVE",
  "latest_version_number": 0,
  "created_at": "..."
}
```

Creation must also create an AgentDraft.

---

# 23. List Agents

## GET `/v1/workspaces/{workspace_id}/agents`

Query parameters:

```text
status
search
limit
cursor
```

Example:

```text
?status=ACTIVE&search=research
```

---

# 24. Get Agent

## GET `/v1/agents/{agent_id}`

Response:

```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "name": "Research Agent",
  "slug": "research-agent",
  "description": "...",
  "status": "ACTIVE",
  "latest_version_number": 3,
  "created_at": "...",
  "updated_at": "..."
}
```

---

# 25. Update Agent Metadata

## PATCH `/v1/agents/{agent_id}`

Request:

```json
{
  "name": "Technical Research Agent",
  "description": "Updated description."
}
```

Does not publish a new AgentVersion.

---

# 26. Archive Agent

## DELETE `/v1/agents/{agent_id}`

MVP semantics:

```text
archive
```

rather than destructive hard deletion.

Response:

```text
204
```

---

# 27. Agent Draft

## GET `/v1/agents/{agent_id}/draft`

Response:

```json
{
  "agent_id": "uuid",
  "instructions": "You are...",
  "model": {
    "provider": "google",
    "name": "gemini-model-name",
    "config": {}
  },
  "runtime_config": {
    "max_steps": 20,
    "max_model_calls": 10,
    "max_tool_calls": 10,
    "max_child_runs": 5,
    "max_agent_depth": 3,
    "max_total_tokens": 100000,
    "timeout_seconds": 120
  },
  "memory_config": {
    "enabled": false
  },
  "updated_at": "..."
}
```

---

# 28. Update Agent Draft

## PATCH `/v1/agents/{agent_id}/draft`

Request may update one or more draft fields.

Example:

```json
{
  "instructions": "You are an expert technical research agent.",
  "model": {
    "provider": "openai",
    "name": "model-name",
    "config": {
      "temperature": 0.1
    }
  }
}
```

Draft changes do not modify existing versions.

---

# 29. Publish Agent Version

## POST `/v1/agents/{agent_id}/versions`

Request:

```json
{
  "change_note": "Add technical research instructions."
}
```

Response `201`:

```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "version_number": 4,
  "created_at": "...",
  "change_note": "Add technical research instructions."
}
```

Publication must be transactional.

---

# 30. List Agent Versions

## GET `/v1/agents/{agent_id}/versions`

Supports:

```text
limit
cursor
```

---

# 31. Get Agent Version

## GET `/v1/agents/{agent_id}/versions/{version_id}`

Response includes immutable resolved configuration.

Example:

```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "version_number": 4,
  "instructions": "...",
  "model": {
    "provider": "google",
    "name": "...",
    "config": {}
  },
  "runtime_config": {},
  "memory_config": {},
  "tools": [],
  "knowledge_bases": [],
  "guardrails": [],
  "child_agents": [],
  "created_at": "..."
}
```

No PATCH endpoint exists for published versions.

---

# 32. Model Catalog

## GET `/v1/models`

Returns supported model definitions.

Example:

```json
{
  "data": [
    {
      "provider": "google",
      "name": "gemini-model-name",
      "display_name": "Gemini ...",
      "capabilities": {
        "tool_calling": true,
        "streaming": true,
        "structured_output": true,
        "vision": true,
        "reasoning": true
      }
    }
  ]
}
```

Model names should come from configured platform registry rather than arbitrary user input where possible.

The Google runtime adapter is implemented behind the platform provider
registry, but Google models are temporarily hidden from the active catalog;
the currently exposed catalog contains only `azure_openai / gpt-5.6-luna`.
When enabled, the adapter calls Google's official GenAI SDK `Interactions` API
with a platform-owned, non-streaming request; provider conversation storage is
disabled because VibesFactory owns session persistence.
Runtime calls use the backend-only `VF_GEMINI_API_KEY` credential and the
official `google-genai` Python SDK; credentials are never part of an agent
draft/version or API response.

---

# 33. Validate Agent Draft

## POST `/v1/agents/{agent_id}/draft:validate`

Useful before publishing.

Response:

```json
{
  "valid": false,
  "errors": [
    {
      "code": "MODEL_TOOL_CALLING_UNSUPPORTED",
      "field": "model.name",
      "message": "Selected model does not support attached tools."
    }
  ],
  "warnings": []
}
```

---

# 34. Sessions

## POST `/v1/agents/{agent_id}/sessions`

Request:

```json
{
  "title": "AgentCore research"
}
```

Response:

```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "title": "AgentCore research",
  "created_at": "..."
}
```

---

# 35. List Sessions

## GET `/v1/agents/{agent_id}/sessions`

Query:

```text
limit
cursor
```

---

# 36. Get Session

## GET `/v1/sessions/{session_id}`

Response:

```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "title": "...",
  "created_at": "...",
  "last_activity_at": "..."
}
```

---

# 37. Session Messages

## GET `/v1/sessions/{session_id}/messages`

Query:

```text
limit
cursor
```

Messages should be ordered consistently.

Response item:

```json
{
  "id": "uuid",
  "role": "USER",
  "content": {
    "type": "text",
    "text": "Explain AgentCore."
  },
  "run_id": "uuid",
  "created_at": "..."
}
```

---

# 38. Create Agent Run

## POST `/v1/agents/{agent_id}/runs`

Used primarily for authenticated playground execution.

Request:

```json
{
  "input": {
    "type": "text",
    "text": "Explain the attached document."
  },
  "session_id": "uuid",
  "agent_version_id": "uuid"
}
```

`agent_version_id` may be omitted for playground execution if the API explicitly resolves:

```text
latest published version
```

Recommended behavior:

- Playground may allow `draft=true`.
- Production/public execution must never use draft.

Safer MVP contract:

```json
{
  "input": {
    "type": "text",
    "text": "..."
  },
  "session_id": "uuid",
  "agent_version_id": "uuid"
}
```

Phase 4 requires `session_id` and `agent_version_id`. The runtime accepts only
text input and always executes the referenced published `AgentVersion`; draft
state and implicit version selection are not accepted by this endpoint.

Response:

```json
{
  "id": "run_uuid",
  "status": "COMPLETED",
  "trace_id": "trace_uuid",
  "output": {
    "type": "text",
    "text": "..."
  },
  "usage": {
    "input_tokens": 1200,
    "output_tokens": 350
  },
  "estimated_cost": "0.00125000",
  "started_at": "...",
  "completed_at": "..."
}
```

---

# 39. Async Agent Run

The same endpoint may accept:

```json
{
  "input": {
    "type": "text",
    "text": "..."
  },
  "agent_version_id": "...",
  "execution_mode": "async"
}
```

Response `202`:

```json
{
  "id": "run_uuid",
  "status": "QUEUED"
}
```

MVP may defer async agent runs until worker infrastructure is ready.

---

# 40. Get Run

## GET `/v1/runs/{run_id}`

Response:

```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "agent_version_id": "uuid",
  "session_id": "uuid",
  "parent_run_id": null,
  "root_run_id": "uuid",
  "status": "COMPLETED",
  "input": {},
  "output": {},
  "usage": {},
  "estimated_cost": "0.0012",
  "error": null,
  "started_at": "...",
  "completed_at": "..."
}
```

---

# 41. Cancel Run

## POST `/v1/runs/{run_id}/cancel`

Response:

```json
{
  "id": "uuid",
  "status": "CANCELLED"
}
```

If already terminal:

```text
409 INVALID_STATE
```

---

# 42. Run Children

## GET `/v1/runs/{run_id}/children`

Returns direct child-agent runs.

Useful for multi-agent UI.

---

# 43. Streaming Agent Run

## POST `/v1/agents/{agent_id}/runs:stream`

Header:

```text
Accept: text/event-stream
```

Request body matches normal run creation.

---

# 44. SSE Event Format

Each event:

```text
id: <event-sequence>
event: <event-type>
data: <json>
```

Example:

```text
event: run.started
data: {"run_id":"...","trace_id":"..."}
```

---

# 45. Core SSE Events

## `run.started`

```json
{
  "run_id": "uuid",
  "trace_id": "uuid",
  "agent_version_id": "uuid"
}
```

## `message.delta`

```json
{
  "run_id": "uuid",
  "delta": "partial text"
}
```

## `message.completed`

```json
{
  "run_id": "uuid",
  "message_id": "uuid"
}
```

## `run.completed`

```json
{
  "run_id": "uuid",
  "status": "COMPLETED",
  "usage": {},
  "estimated_cost": "0.0012"
}
```

## `run.failed`

```json
{
  "run_id": "uuid",
  "error": {
    "code": "PROVIDER_ERROR",
    "message": "Model provider failed."
  }
}
```

## Tool events

Phase 6 adds `tool.started`, `tool.completed`, and `tool.failed`. Payloads contain only sanitized identifiers and execution status; provider payloads and credentials are never included.

```json
{
  "run_id": "uuid",
  "tool_id": "uuid",
  "tool_version_id": "uuid",
  "tool": "web_search",
  "status": "running",
  "duration_ms": 120
}
```

---

# 46. Extended SSE Events

Later phases add:

```text
model.started
model.completed

tool.started
tool.completed
tool.failed

knowledge.retrieved

memory.retrieved

guardrail.triggered

approval.requested

child_agent.started
child_agent.completed

workflow.node_started
workflow.node_completed
```

Frontend must ignore unknown event types for forward compatibility.

---

# 47. Tools

Built-in Function tools available in every workspace are `calculator`, `current_datetime`, `echo`, and `web_search`. Built-ins have immutable platform-managed versions and are catalog-ready but never auto-attached. `web_search` accepts `{ "query": "...", "num_results": 10 }` and returns only `query`, normalized `results` (`title`, `url`, `published_date`, `highlights`) and an optional `request_id`.

## POST `/v1/workspaces/{workspace_id}/tools`

Request:

```json
{
  "name": "Weather",
  "slug": "weather",
  "description": "Gets current weather.",
  "type": "HTTP"
}
```

Response:

```json
{
  "id": "uuid",
  "name": "Weather",
  "type": "HTTP",
  "latest_version_number": 0
}
```

---

# 48. List Tools

## GET `/v1/workspaces/{workspace_id}/tools`

Filters:

```text
type
status
search
```

The response is a collection envelope:

```json
{
  "data": [],
  "pagination": {"next_cursor": null, "has_more": false}
}
```

`built_in` is persisted platform state. Built-in slugs are reserved, their
versions are immutable, and catalog seeding never creates an agent binding.
Tool and version resources are returned only after workspace authorization.

---

# 49. Publish Tool Version

## POST `/v1/tools/{tool_id}/versions`

Request example for HTTP Tool:

```json
{
  "name": "get_weather",
  "description": "Gets weather for a city.",
  "input_schema": {
    "type": "object",
    "properties": {
      "city": {
        "type": "string"
      }
    },
    "required": ["city"]
  },
  "output_schema": {
    "type": "object"
  },
  "executor": {
    "type": "HTTP",
    "config": {
      "method": "GET",
      "base_url": "https://example.com",
      "path": "/weather",
      "query_mapping": {
        "city": "{{city}}"
      },
      "credential_ref": "uuid",
      "credential_binding": {
        "location": "HEADER",
        "name": "Authorization",
        "prefix": "Bearer",
        "secret_key": "token"
      }
    }
  },
  "timeout_seconds": 10,
  "retry_policy": {
    "max_attempts": 2
  },
  "risk_level": "LOW",
  "side_effect": false,
  "idempotent": true
}
```

Response `201`.

---

# 50. Get Tool Version

## GET `/v1/tools/{tool_id}/versions/{version_id}`

Published tool versions are immutable.

HTTP executor configuration is canonicalized to `method`, `base_url`, `path`,
`headers`, `query_mapping`, and `body_mapping`. Legacy `url` input is accepted
as a compatibility fallback and normalized at write time. Mappings support
only `{{field}}` placeholders. Redirects, embedded URL credentials, sensitive
headers, private destinations, oversized responses, and unresolved mappings
are rejected with stable errors such as `HTTP_URL_INVALID`,
`HTTP_PRIVATE_DESTINATION`, `HTTP_RESPONSE_TOO_LARGE`, and `HTTP_TIMEOUT`.

---

# 51. Test Tool

## POST `/v1/tool-versions/{tool_version_id}:test`

Request:

```json
{
  "arguments": {
    "city": "Ho Chi Minh City"
  }
}
```

Response:

```json
{
  "status": "completed",
  "output": {},
  "duration_ms": 310
}
```

This endpoint must enforce the same validation and security controls as runtime execution.

---

# 52. Attach Tool to Agent Draft

## POST `/v1/agents/{agent_id}/draft/tools`

Request:

```json
{
  "tool_version_id": "uuid",
  "alias": "weather"
}
```

---

# 53. Remove Tool from Agent Draft

## DELETE `/v1/agents/{agent_id}/draft/tools/{tool_version_id}`

Response:

```text
204
```

---

# 54. Credentials

## POST `/v1/workspaces/{workspace_id}/credentials`

Request:

```json
{
  "name": "GitHub API",
  "provider": "github",
  "type": "API_KEY",
  "secret": {
    "token": "secret-value"
  },
  "metadata": {}
}
```

Response must never return the secret:

```json
{
  "id": "uuid",
  "name": "GitHub API",
  "provider": "github",
  "type": "API_KEY",
  "created_at": "..."
}
```

---

# 55. List Credentials

## GET `/v1/workspaces/{workspace_id}/credentials`

Returns metadata only.

---

# 56. Delete/Revoke Credential

## DELETE `/v1/credentials/{credential_id}`

Semantics:

```text
revoke
```

Response:

```text
204
```

---

# 57. Credential Secret Rotation

## POST `/v1/credentials/{credential_id}:rotate`

Request:

```json
{
  "secret": {
    "token": "new-secret"
  }
}
```

Old secret should become inaccessible after successful rotation.

Credential create, list, rotate and revoke operations never return plaintext
secrets, ciphertext or encryption key material. Members can list credential
metadata; only workspace owners can create, rotate or revoke credentials.

## GET `/v1/credentials/{credential_id}/keys`

Returns the top-level key names available in an active credential for legacy
credential snapshots and diagnostics. The MCP UI now binds each custom header
to a Secret Store credential directly:

```json
{
  "credential_id": "uuid",
  "keys": ["instance", "password", "token", "username"]
}
```

Only key names are returned; values are decrypted only inside the executor
when the outbound MCP request is created.

---

# 58. MCP Servers

Phase 8 additionally supports `GET`/`PATCH`/soft-`DELETE` for MCP server
management and `GET /v1/mcp-servers/{mcp_server_id}/tools` for the persisted
discovery catalog. Mutating MCP server, test, discovery and import operations
are owner-only because endpoint configuration can cause SSRF or credential
exfiltration; members may view servers and attach already imported versions to
agent drafts. MCP imports are immutable snapshots and rediscovery reports
schema drift rather than changing published AgentVersions.

## POST `/v1/workspaces/{workspace_id}/mcp-servers`

Request:

```json
{
  "name": "GitHub MCP",
  "transport": "STREAMABLE_HTTP",
  "endpoint": "https://mcp.example.com",
  "credential_id": "uuid",
  "auth": {
    "mode": "BEARER",
    "header_name": "Authorization",
    "prefix": "Bearer",
    "secret_key": "token",
    "custom_headers": [
      { "header_name": "x-instance", "credential_id": "uuid" },
      { "header_name": "x-username", "credential_id": "uuid" },
      { "header_name": "x-password", "credential_id": "uuid" }
    ]
  }
}
```

`custom_headers` is independent from Authorization, so a server may receive
both the Bearer header and additional headers in the same request. It contains
only references to Secret Store credentials (one header may use a different
credential from another). Plaintext header values are never accepted in this
request or persisted in the MCP server configuration. At connection time the
executor resolves each `credential_id` and sends its vault token under the
configured `header_name`. Legacy snapshots may use `secret_key` against the
primary credential. Custom headers can also be used with `mode: "NONE"` and do
not require a primary Authorization credential. `prefix` is optional and
defaults to an empty string.

Response:

```json
{
  "id": "uuid",
  "name": "GitHub MCP",
  "status": "ACTIVE"
}
```

---

# 59. List MCP Servers

## GET `/v1/workspaces/{workspace_id}/mcp-servers`

---

# 60. Test MCP Server

## POST `/v1/mcp-servers/{mcp_server_id}:test`

Response:

```json
{
  "status": "CONNECTED",
  "latency_ms": 140
}
```

---

# 61. Discover MCP Tools

## POST `/v1/mcp-servers/{mcp_server_id}:discover`

Response:

```json
{
  "tools": [
    {
      "name": "search_issues",
      "description": "...",
      "input_schema": {}
    }
  ]
}
```

Discovery may persist/update local catalog.

---

# 62. Import MCP Tool

## POST `/v1/mcp-servers/{mcp_server_id}/tools:import`

Request:

```json
{
  "remote_name": "search_issues",
  "tool_name": "GitHub Issue Search",
  "slug": "github-issue-search"
}
```

Creates a VibesFactory Tool and ToolVersion of type:

```text
MCP
```

---

# 63. Knowledge Bases

## POST `/v1/workspaces/{workspace_id}/knowledge-bases`

Request:

```json
{
  "name": "Product Documentation",
  "description": "Internal technical documentation.",
  "embedding": {
    "provider": "google",
    "model": "embedding-model-name"
  }
}
```

Response `201`.

---

# 64. List Knowledge Bases

## GET `/v1/workspaces/{workspace_id}/knowledge-bases`

Optional query parameter `status=ACTIVE|ARCHIVED` filters the collection before
pagination. Knowledge and Agent configuration UIs request `status=ACTIVE`, so
archived knowledge bases remain recoverable through the API but are hidden from
normal selection and listing views.

---

# 65. Get Knowledge Base

## GET `/v1/knowledge-bases/{knowledge_base_id}`

Response includes document counts/status summary.

---

# 66. Upload Document

## POST `/v1/knowledge-bases/{knowledge_base_id}/documents`

Content type:

```text
multipart/form-data
```

Fields:

```text
file
metadata optional
```

Response `202`:

```json
{
  "id": "document_uuid",
  "name": "manual.pdf",
  "status": "UPLOADED",
  "created_at": "..."
}
```

The API must not wait for embedding completion.

---

# 67. List Documents

## GET `/v1/knowledge-bases/{knowledge_base_id}/documents`

Filters:

```text
status
search
```

---

# 68. Get Document

## GET `/v1/documents/{document_id}`

Response:

```json
{
  "id": "uuid",
  "knowledge_base_id": "uuid",
  "name": "manual.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 1200000,
  "status": "READY",
  "error": null,
  "created_at": "..."
}
```

---

# 69. Reprocess Document

## POST `/v1/documents/{document_id}:reprocess`

Response `202`:

```json
{
  "id": "uuid",
  "status": "PROCESSING"
}
```

Must be idempotent or protected against concurrent duplicate ingestion.

---

# 70. Delete Document

## DELETE `/v1/documents/{document_id}`

May mark:

```text
DELETED
```

and asynchronously clean chunks/blob.

---

# 71. Search Knowledge Base

Useful debug endpoint.

## POST `/v1/knowledge-bases/{knowledge_base_id}:search`

Request:

```json
{
  "query": "How does authentication work?",
  "top_k": 5,
  "filters": {}
}
```

Response:

```json
{
  "results": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "content": "...",
      "score": 0.84,
      "source_name": "manual.pdf",
      "page_number": 12,
      "metadata": {}
    }
  ]
}
```

---

# 72. Attach Knowledge Base to Agent Draft

## POST `/v1/agents/{agent_id}/draft/knowledge-bases`

Request:

```json
{
  "knowledge_base_id": "uuid",
  "mode": "auto",
  "top_k": 5,
  "score_threshold": 0.6,
  "filters": {
    "document_ids": [],
    "metadata": {}
  }
}
```

---

# 73. Remove Knowledge Base

## DELETE `/v1/agents/{agent_id}/draft/knowledge-bases/{knowledge_base_id}`

---

# 74. Memory Stores

## POST `/v1/workspaces/{workspace_id}/memory-stores`

Request:

```json
{
  "name": "User Memory",
  "description": "Long-term user preferences.",
  "embedding": {
    "provider": "google",
    "model": "embedding-model-name"
  }
}
```

---

# 75. List Memory Stores

## GET `/v1/workspaces/{workspace_id}/memory-stores`

---

# 76. List Memory Items

## GET `/v1/memory-stores/{memory_store_id}/items`

Filters:

```text
user_id
agent_id
type
limit
cursor
```

Response item:

```json
{
  "id": "uuid",
  "type": "PROFILE",
  "content": "User prefers Python.",
  "importance": 0.8,
  "confidence": 0.95,
  "user_id": "uuid",
  "agent_id": null,
  "created_at": "..."
}
```

---

# 77. Create Memory Manually

## POST `/v1/memory-stores/{memory_store_id}/items`

Request:

```json
{
  "user_id": "uuid",
  "agent_id": null,
  "type": "PROFILE",
  "content": "User prefers Python."
}
```

Useful for testing/admin.

---

# 78. Update Memory

## PATCH `/v1/memory-items/{memory_item_id}`

Request:

```json
{
  "content": "User prefers Python and FastAPI."
}
```

Should regenerate embedding if content changes.

---

# 79. Delete Memory

## DELETE `/v1/memory-items/{memory_item_id}`

MVP may soft-delete.

---

# 80. Search Memory

## POST `/v1/memory-stores/{memory_store_id}:search`

Request:

```json
{
  "query": "preferred programming language",
  "user_id": "uuid",
  "agent_id": null,
  "top_k": 5
}
```

---

# 81. Agent Memory Configuration

## PATCH `/v1/agents/{agent_id}/draft/memory`

Request:

```json
{
  "enabled": true,
  "memory_store_id": "uuid",
  "retrieve": {
    "top_k": 5
  },
  "write": {
    "enabled": true,
    "types": [
      "PROFILE",
      "SEMANTIC"
    ]
  }
}
```

---

# 82. Guardrails

## POST `/v1/workspaces/{workspace_id}/guardrails`

Request:

```json
{
  "name": "Default Safety",
  "description": "Default runtime policies."
}
```

## GET `/v1/workspaces/{workspace_id}/guardrails`

Returns the workspace policy catalog with latest version and usage metadata.

## GET `/v1/guardrails/{policy_id}`

Returns one policy when the caller belongs to its workspace.

---

# 83. Publish Guardrail Version

## POST `/v1/guardrails/{policy_id}/versions`

Request:

```json
{
  "type": "RULE_SET",
  "configuration": {
    "rules": [
      {
        "id": "block-high-risk-side-effects",
        "type": "TOOL_POLICY",
        "hooks": ["TOOL_INPUT"],
        "minimum_risk": "HIGH",
        "side_effect_only": true,
        "action": "BLOCK"
      }
    ]
  }
}
```

Guardrail versions are immutable and version numbers are assigned by the server.
Supported rule types are `REGEX`, `SECRET_DETECTION`, `PII_REDACTION`,
`TOOL_POLICY`, and `MAX_PAYLOAD_SIZE`. Tool-version references must belong to
the policy workspace; invalid or unsafe regular expressions return `422`.

## GET `/v1/guardrails/{policy_id}/versions`

Lists immutable versions in descending version order.

## GET `/v1/guardrails/{policy_id}/versions/{version_id}`

Returns one immutable version and its complete structured configuration.

---

# 84. Attach Guardrail to Agent Draft

## POST `/v1/agents/{agent_id}/draft/guardrails`

Request:

```json
{
  "guardrail_version_id": "uuid",
  "hook": "TOOL_INPUT",
  "priority": 100
}
```

## GET `/v1/agents/{agent_id}/draft/guardrails`

Returns `guardrails_enabled` plus custom bindings grouped by hook. The
platform baseline is always shown read-only and uses `baseline_version: 1`.

## PATCH `/v1/agents/{agent_id}/draft/guardrails/settings`

Request: `{ "enabled": true }`. The setting applies only to future published
versions; disabling it preserves configured bindings and does not disable core
authentication, authorization, budgets, schema validation, redaction, or
executor limits.

## DELETE `/v1/agents/{agent_id}/draft/guardrails/{guardrail_version_id}/{hook}`

Detaches a draft binding. Duplicate attachments return `409`; incompatible
tool-policy hooks return `422`; cross-workspace resources are normalized to
`404`.

---

# 85. Workflows

## POST `/v1/workspaces/{workspace_id}/workflows`

Request:

```json
{
  "name": "Research Workflow",
  "slug": "research-workflow",
  "description": "Research and summarize."
}
```

---

# 86. Workflow Draft

## GET `/v1/workflows/{workflow_id}/draft`

Example:

```json
{
  "nodes": [
    {
      "key": "start",
      "type": "START",
      "name": "Start",
      "config": {}
    },
    {
      "key": "research",
      "type": "AGENT",
      "name": "Research",
      "config": {
        "agent_id": "uuid",
        "agent_version_id": "uuid"
      }
    }
  ],
  "edges": [
    {
      "source": "start",
      "target": "research"
    }
  ]
}
```

---

# 87. Update Workflow Draft

## PUT `/v1/workflows/{workflow_id}/draft`

Full draft replacement is preferred initially.

Request:

```json
{
  "nodes": [],
  "edges": []
}
```

This simplifies graph editing consistency.

---

# 88. Validate Workflow Draft

## POST `/v1/workflows/{workflow_id}/draft:validate`

Response:

```json
{
  "valid": false,
  "errors": [
    {
      "code": "UNREACHABLE_NODE",
      "node_key": "writer"
    }
  ]
}
```

Validation should detect:

```text
missing START

missing END

invalid edges

missing resources

cycles if unsupported

unreachable nodes
```

---

# 89. Publish Workflow Version

## POST `/v1/workflows/{workflow_id}/versions`

Creates immutable graph.

---

# 90. Run Workflow

## POST `/v1/workflows/{workflow_id}/runs`

Request:

```json
{
  "workflow_version_id": "uuid",
  "input": {
    "topic": "AgentCore"
  },
  "execution_mode": "sync"
}
```

Response:

```json
{
  "id": "workflow_run_uuid",
  "status": "COMPLETED",
  "trace_id": "uuid",
  "output": {}
}
```

---

# 91. Get Workflow Run

## GET `/v1/workflow-runs/{workflow_run_id}`

Includes:

```text
status
current_node_name
input
output
variables
waiting_reason
timestamps
```

---

# 92. Workflow Node Runs

## GET `/v1/workflow-runs/{workflow_run_id}/nodes`

Response:

```json
{
  "data": [
    {
      "id": "uuid",
      "node_key": "research",
      "node_name": "Research topic",
      "status": "COMPLETED",
      "agent_run_id": "uuid",
      "usage": {
        "input_tokens": 120,
        "output_tokens": 240,
        "total_tokens": 360
      },
      "duration_ms": 1820,
      "started_at": "...",
      "completed_at": "..."
    }
  ]
}
```

---

# 92A. Workflow Run History

## GET `/v1/workflows/{workflow_id}/runs?limit=50`

Returns recent runs for the workflow, ordered newest first. Each summary
includes the terminal status, current node display name, usage and timestamps.
The endpoint is workspace-scoped and only returns runs visible to the caller.

---

# 93. Child Agents

## POST `/v1/agents/{agent_id}/draft/child-agents`

Request:

```json
{
  "child_agent_id": "uuid",
  "child_agent_version_id": "uuid",
  "alias": "research",
  "description": "Research technical topics."
}
```

Published AgentVersion should preferably pin:

```text
child_agent_version_id
```

for reproducibility.

---

# 94. Remove Child Agent

## DELETE `/v1/agents/{agent_id}/draft/child-agents/{child_agent_id}`

---

# 95. Approval Requests

## GET `/v1/workspaces/{workspace_id}/approval-requests`

Filters:

```text
status
run_id
workflow_run_id
```

---

# 96. Get Approval Request

## GET `/v1/approval-requests/{approval_id}`

Response:

```json
{
  "id": "uuid",
  "status": "PENDING",
  "requested_action": "delete_repository",
  "arguments": {
    "repository": "example"
  },
  "risk_reason": "High-risk destructive tool.",
  "run_id": "uuid",
  "requested_at": "..."
}
```

Sensitive credential data must not appear in arguments.

---

# 97. Approve

## POST `/v1/approval-requests/{approval_id}/approve`

Request:

```json
{
  "comment": "Approved."
}
```

Response:

```json
{
  "id": "uuid",
  "status": "APPROVED",
  "resolved_at": "..."
}
```

Runtime then resumes exact persisted action.

---

# 98. Reject

## POST `/v1/approval-requests/{approval_id}/reject`

Request:

```json
{
  "comment": "Operation is not allowed."
}
```

---

# 99. Evaluation Datasets

## POST `/v1/workspaces/{workspace_id}/evaluation-datasets`

Request:

```json
{
  "name": "Research Agent Regression",
  "description": "Core behavior regression suite."
}
```

---

# 100. Evaluation Cases

## POST `/v1/evaluation-datasets/{dataset_id}/cases`

Request:

```json
{
  "input": {
    "type": "text",
    "text": "What does the refund policy say?"
  },
  "expected_output": null,
  "expected_tool": "search_knowledge",
  "expected_schema": null,
  "rubric": "Answer must be grounded in the provided knowledge."
}
```

---

# 101. List Evaluation Cases

## GET `/v1/evaluation-datasets/{dataset_id}/cases`

Supports pagination.

---

# 102. Update Evaluation Case

## PATCH `/v1/evaluation-cases/{case_id}`

---

# 103. Delete Evaluation Case

## DELETE `/v1/evaluation-cases/{case_id}`

---

# 104. Start Evaluation Run

## POST `/v1/evaluation-datasets/{dataset_id}/runs`

Request:

```json
{
  "agent_version_id": "uuid",
  "evaluators": [
    {
      "type": "TOOL_CALL"
    },
    {
      "type": "LATENCY",
      "config": {
        "max_ms": 10000
      }
    },
    {
      "type": "LLM_JUDGE",
      "config": {
        "criteria": [
          "correctness",
          "groundedness"
        ]
      }
    }
  ]
}
```

Response `202`:

```json
{
  "id": "evaluation_run_uuid",
  "status": "QUEUED"
}
```

---

# 105. Get Evaluation Run

## GET `/v1/evaluation-runs/{evaluation_run_id}`

Response:

```json
{
  "id": "uuid",
  "agent_version_id": "uuid",
  "status": "COMPLETED",
  "aggregate_metrics": {
    "pass_rate": 0.9,
    "average_latency_ms": 2800,
    "average_cost": 0.003
  },
  "started_at": "...",
  "completed_at": "..."
}
```

---

# 106. Evaluation Results

## GET `/v1/evaluation-runs/{evaluation_run_id}/results`

Each result:

```json
{
  "case_id": "uuid",
  "run_id": "uuid",
  "evaluator": "TOOL_CALL",
  "score": 1,
  "passed": true,
  "details": {}
}
```

---

# 107. Compare Evaluation Runs

## POST `/v1/evaluation-runs:compare`

Request:

```json
{
  "baseline_run_id": "uuid",
  "candidate_run_id": "uuid"
}
```

Response:

```json
{
  "baseline": {
    "agent_version_id": "uuid"
  },
  "candidate": {
    "agent_version_id": "uuid"
  },
  "deltas": {
    "pass_rate": 0.08,
    "average_latency_ms": 320,
    "estimated_cost": 0.0004
  }
}
```

Both runs should normally use the same dataset.

---

# 108. Deployments

## POST `/v1/workspaces/{workspace_id}/deployments`

Request:

```json
{
  "name": "Research Production",
  "slug": "research-production",
  "agent_id": "uuid",
  "agent_version_id": "uuid",
  "environment": "PRODUCTION"
}
```

Response `201`.

---

# 109. List Deployments

## GET `/v1/workspaces/{workspace_id}/deployments`

Filters:

```text
environment
status
agent_id
```

---

# 110. Get Deployment

## GET `/v1/deployments/{deployment_id}`

---

# 111. Change Deployment Version

## PATCH `/v1/deployments/{deployment_id}`

Request:

```json
{
  "agent_version_id": "previous-version-uuid"
}
```

This is the rollback/deployment promotion mechanism.

---

# 112. Disable Deployment

## POST `/v1/deployments/{deployment_id}:disable`

---

# 113. Enable Deployment

## POST `/v1/deployments/{deployment_id}:enable`

---

# 114. API Keys

## POST `/v1/deployments/{deployment_id}/api-keys`

Request:

```json
{
  "name": "Production Client",
  "expires_at": null
}
```

Response:

```json
{
  "id": "uuid",
  "name": "Production Client",
  "key": "vf_live_xxxxxxxxxxxxx",
  "key_prefix": "vf_live_abcd",
  "created_at": "..."
}
```

The raw `key` must appear exactly once.

---

# 115. List API Keys

## GET `/v1/deployments/{deployment_id}/api-keys`

Response excludes raw key.

---

# 116. Revoke API Key

## DELETE `/v1/api-keys/{api_key_id}`

Response:

```text
204
```

---

# 117. Public Deployment Invocation

## POST `/v1/deployments/{deployment_id}/runs`

Authentication:

```text
VibesFactory API key
```

Request:

```json
{
  "input": {
    "type": "text",
    "text": "Research production agent platforms."
  },
  "session_id": null,
  "stream": false,
  "metadata": {
    "external_user_id": "customer-123"
  }
}
```

Response:

```json
{
  "id": "run_uuid",
  "status": "COMPLETED",
  "output": {
    "type": "text",
    "text": "..."
  },
  "usage": {},
  "estimated_cost": "0.003",
  "created_at": "..."
}
```

Deployment always determines the AgentVersion.

Clients cannot override:

```text
agent_version_id
```

on this endpoint.

---

# 118. Public Streaming Invocation

## POST `/v1/deployments/{deployment_id}/runs:stream`

Uses API key plus SSE.

Same runtime logic as authenticated streaming endpoint.

---

# 119. Traces

## GET `/v1/traces`

List persisted traces visible to the authenticated user across their workspace memberships.

Query parameters:

```text
agent_id
session_id             # returns every execution trace for one session
agent          # matches agent name or slug
status         # RUNNING | COMPLETED | FAILED
started_after
started_before
limit
cursor
```

The response follows the standard collection contract and includes the owning agent, run/session IDs, timestamps, duration, safe input/output previews, and normalized error code. Credentials, provider secrets, and raw exceptions are never included.

```json
{
  "data": [
    {
      "id": "trace_uuid",
      "agent_id": "agent_uuid",
      "agent_name": "Research Agent",
      "agent_version_id": "version_uuid",
      "run_id": "run_uuid",
      "session_id": "session_uuid",
      "status": "COMPLETED",
      "started_at": "...",
      "completed_at": "...",
      "duration_ms": 920,
      "input_text": "Hello",
      "output_text": "Hi there",
      "error_code": null
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false
  }
}
```

## GET `/v1/runs/{run_id}/trace`

Response:

```json
{
  "trace": {
    "id": "uuid",
    "status": "COMPLETED",
    "started_at": "...",
    "completed_at": "..."
  },
  "root_span": {
    "id": "uuid"
  }
}
```

For large traces, avoid embedding all spans by default.

---

# 120. Trace Spans

## GET `/v1/traces/{trace_id}/spans`

Query:

```text
limit
cursor
type
run_id
```

Response item:

```json
{
  "id": "uuid",
  "parent_span_id": "uuid",
  "run_id": "uuid",
  "type": "MODEL",
  "name": "google.generate",
  "status": "COMPLETED",
  "started_at": "...",
  "completed_at": "...",
  "duration_ms": 920,
  "usage": {
    "input_tokens": 1030,
    "output_tokens": 214,
    "total_tokens": 1244,
    "cached_input_tokens": 0
  },
  "attributes": {
    "provider": "google",
    "model": "..."
  }
}
```

---

# 121. Span Detail

## GET `/v1/spans/{span_id}`

Response may include redacted:

```text
input
output
error
attributes
usage
```

`usage` is a normalized per-span token breakdown. A `CONTEXT_BUILD` span uses
`input_tokens_estimated: true` when the value comes from the platform tokenizer
estimate rather than provider-reported usage. Provider credentials and raw
provider exceptions must not be present in any span payload.

Do not expose unbounded payloads.

---

# 122. Monitoring Summary

## GET `/v1/workspaces/{workspace_id}/monitoring/summary`

Query:

```text
from
to
agent_id
agent_version_id
provider
model
```

Response:

```json
{
  "period": {
    "from": "...",
    "to": "..."
  },
  "runs": {
    "total": 8291,
    "completed": 8018,
    "failed": 273,
    "success_rate": 0.967
  },
  "latency": {
    "average_ms": 2400,
    "p95_ms": 6800
  },
  "usage": {
    "input_tokens": 1000000,
    "output_tokens": 300000
  },
  "estimated_cost": "12.48",
  "tool_failure_rate": 0.012
}
```

---

# 123. Monitoring Timeseries

## GET `/v1/workspaces/{workspace_id}/monitoring/timeseries`

Query:

```text
metric
from
to
interval
agent_id
```

Possible metrics:

```text
runs
failures
latency
tokens
estimated_cost
tool_failures
```

Response:

```json
{
  "metric": "runs",
  "interval": "1h",
  "points": [
    {
      "timestamp": "...",
      "value": 14
    }
  ]
}
```

---

# 124. Runs List

## GET `/v1/workspaces/{workspace_id}/runs`

Filters:

```text
agent_id
agent_version_id
deployment_id
status
root_run_id
from
to
limit
cursor
```

This is one of the most important operational APIs.

---

# 125. Audit Logs

## GET `/v1/workspaces/{workspace_id}/audit-logs`

Filters:

```text
actor_user_id
action
resource_type
resource_id
from
to
```

Response:

```json
{
  "data": [
    {
      "id": "uuid",
      "actor_user_id": "uuid",
      "action": "agent.version.published",
      "resource_type": "agent",
      "resource_id": "uuid",
      "created_at": "..."
    }
  ]
}
```

---

# 126. Model Provider Credentials

BYOK model credentials may use the normal Credential API.

Example provider:

```text
openai
google
anthropic
```

Agent draft model configuration references:

```text
credential_id
```

or platform default credentials if configured.

Never accept a raw API key directly inside an Agent draft.

---

# 127. Model Provider Test

## POST `/v1/credentials/{credential_id}:test-provider`

Request:

```json
{
  "provider": "openai"
}
```

Response:

```json
{
  "status": "VALID"
}
```

Use sparingly; avoid unnecessary billable model requests.

---

# 128. Agent Draft Tool Response

Recommended:

## GET `/v1/agents/{agent_id}/draft/tools`

Response:

```json
{
  "data": [
    {
      "tool_id": "uuid",
      "tool_version_id": "uuid",
      "name": "Weather",
      "alias": "weather",
      "type": "HTTP"
    }
  ]
}
```

---

# 129. Agent Draft Knowledge Response

## GET `/v1/agents/{agent_id}/draft/knowledge-bases`

---

# 130. Agent Draft Guardrails Response

## GET `/v1/agents/{agent_id}/draft/guardrails`

---

# 131. Agent Draft Child Agents Response

## GET `/v1/agents/{agent_id}/draft/child-agents`

These separate sub-resource APIs simplify frontend editing.

---

# 132. Async Job API

Internal/administrative visibility may use:

## GET `/v1/jobs/{job_id}`

Response:

```json
{
  "id": "uuid",
  "type": "DOCUMENT_INGESTION",
  "status": "COMPLETED",
  "attempt_count": 1,
  "created_at": "...",
  "completed_at": "..."
}
```

This API may remain internal in MVP.

---

# 133. Job Status Values

```text
QUEUED
RUNNING
COMPLETED
FAILED
CANCELLED
```

---

# 134. Search and Filtering Conventions

Text search query:

```text
search
```

rather than varying between:

```text
q
query
search_text
```

Dates:

```text
from
to
```

Status:

```text
status
```

Sorting default should be deterministic.

Operational resources generally use:

```text
created_at DESC
```

---

# 135. Field Selection

Do not implement GraphQL-style field selection in MVP.

Responses should have stable shapes.

---

# 136. Partial Update Semantics

Use:

```text
PATCH
```

for partial updates.

Use:

```text
PUT
```

only when replacing a complete resource representation, such as Workflow Draft graph.

---

# 137. Delete Semantics

Endpoints may internally archive/revoke/soft-delete while still exposing HTTP:

```text
DELETE
```

The product behavior must be documented per resource.

Examples:

```text
Agent DELETE
→ archive

Credential DELETE
→ revoke

API Key DELETE
→ revoke
```

---

# 138. Resource Conflict Examples

Return `409` for:

```text
duplicate workspace slug

duplicate agent slug

publishing invalid concurrent version

approving an already rejected request

cancelling completed run

reusing idempotency key with different payload
```

---

# 139. Validation Error

Example:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "request_id": "req_123",
    "details": {
      "fields": [
        {
          "field": "runtime_config.max_steps",
          "message": "Must be between 1 and 100."
        }
      ]
    }
  }
}
```

---

# 140. Provider Errors

Do not expose:

```text
OpenAI SDK exception class
Google SDK traceback
```

Normalize:

```json
{
  "error": {
    "code": "PROVIDER_RATE_LIMITED",
    "message": "The configured model provider is temporarily rate limited.",
    "request_id": "..."
  }
}
```

Detailed provider error information may be placed in protected Trace metadata after redaction.

---

# 141. Tool Errors

Example runtime error:

```json
{
  "error": {
    "code": "TOOL_EXECUTION_FAILED",
    "message": "Tool execution failed.",
    "request_id": "..."
  }
}
```

Run trace preserves:

```text
tool name
duration
normalized reason
```

---

# 142. Rate Limit Response

HTTP:

```text
429
```

Headers may include:

```text
Retry-After
```

Body:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests.",
    "request_id": "..."
  }
}
```

---

# 143. API Key Format

Recommended VibesFactory key prefix:

```text
vf_live_
```

and future:

```text
vf_test_
```

Example:

```text
vf_live_7h29f...
```

Store only:

```text
prefix
hash
```

after creation.

---

# 144. Input Content Model

Initial input:

```json
{
  "type": "text",
  "text": "..."
}
```

Future-compatible shape:

```json
{
  "parts": [
    {
      "type": "text",
      "text": "..."
    }
  ]
}
```

Core runtime domain should not assume plain string forever.

---

# 145. Output Content Model

Initial response:

```json
{
  "type": "text",
  "text": "..."
}
```

Metadata may include:

```json
{
  "citations": [],
  "structured_output": null
}
```

---

# 146. Usage Model

Normalized API usage:

```json
{
  "input_tokens": 1000,
  "output_tokens": 250,
  "cached_input_tokens": 0,
  "total_tokens": 1250
}
```

Provider-specific usage remains in internal metadata if needed.

---

# 147. Run Error Model

A GET Run should expose normalized failure:

```json
{
  "id": "uuid",
  "status": "FAILED",
  "error": {
    "code": "TOOL_TIMEOUT",
    "message": "The tool exceeded its timeout."
  }
}
```

Do not require clients to query Trace just to learn basic failure status.

---

# 148. Run Status Transitions

Valid conceptual transitions:

```text
QUEUED
  ↓
RUNNING
  ↓
WAITING_TOOL
  ↓
RUNNING
```

or:

```text
RUNNING
 ↓
WAITING_APPROVAL
 ↓
RUNNING
```

terminal:

```text
COMPLETED
FAILED
CANCELLED
```

Invalid transitions should produce:

```text
409 INVALID_STATE
```

---

# 149. Document Status API Semantics

Status sequence:

```text
UPLOADED
 ↓
PROCESSING
 ↓
READY
```

or:

```text
PROCESSING
 ↓
FAILED
```

Reprocess:

```text
FAILED / READY
 ↓
PROCESSING
```

---

# 150. Evaluation Status

```text
QUEUED
 ↓
RUNNING
 ↓
COMPLETED
```

or:

```text
FAILED
CANCELLED
```

---

# 151. Approval Status

```text
PENDING
 ↓
APPROVED
```

or:

```text
REJECTED
EXPIRED
```

Terminal approvals cannot be modified.

---

# 152. Workspace Isolation Rule

For any URL such as:

```text
/v1/agents/{agent_id}
```

backend must effectively enforce:

```text
agent.workspace_id
in authenticated user's memberships
```

Returning:

```text
404
```

instead of `403` for inaccessible resources may be preferred to avoid leaking resource existence.

Use one consistent security convention.

Recommended:

```text
404 for inaccessible workspace resources
```

except explicit workspace membership APIs.

---

# 153. Optimistic Concurrency

MVP may omit full ETags.

For high-conflict mutable draft resources, consider:

```text
updated_at
```

or:

```text
revision
```

later.

Initial solo-user development does not require advanced optimistic locking everywhere.

---

# 154. Agent Draft Revision

Recommended future-compatible response:

```json
{
  "revision": 12,
  "updated_at": "..."
}
```

PATCH could later support:

```text
If-Match
```

but this is not required for MVP.

---

# 155. CORS

Production API should permit only configured frontend origins.

Do not use:

```text
Access-Control-Allow-Origin: *
```

for authenticated management APIs.

Public deployment APIs may use separate CORS policies.

---

# 156. OpenAPI

FastAPI-generated OpenAPI must be available in non-production or controlled production mode.

Expected:

```text
/openapi.json
/docs
```

Production `/docs` exposure may be configurable.

---

# 157. Schema Naming

Pydantic/OpenAPI models should use stable names such as:

```text
AgentCreateRequest
AgentResponse

AgentDraftUpdateRequest

AgentVersionResponse

RunCreateRequest
RunResponse

ToolCreateRequest
ToolVersionCreateRequest

KnowledgeBaseCreateRequest

EvaluationRunCreateRequest
```

Avoid anonymous or generic names such as:

```text
Payload
Data
RequestModel
```

---

# 158. Internal IDs vs User Slugs

Use UUIDs for API relationships.

Slugs may support friendly navigation.

Do not use mutable names as foreign identifiers.

Example:

```text
agent_id
```

is canonical.

---

# 159. API Logging

Management/API logs should capture:

```text
request_id
method
path template
status
duration
user_id where appropriate
workspace_id where appropriate
```

Never log:

```text
Authorization
API keys
Credential secret payloads
```

---

# 160. Public API Metadata

Public deployment requests may accept client metadata:

```json
{
  "metadata": {
    "external_user_id": "customer-42",
    "conversation_source": "website"
  }
}
```

Limits:

- Maximum key count
- Maximum value size
- No reserved internal keys

Metadata is untrusted.

---

# 161. External User Identity

VibesFactory public API should not automatically create internal `users` records for arbitrary external customers.

Instead external identity may live in Run/Session metadata:

```text
external_user_id
```

Future public-user memory architecture may introduce a dedicated external principal model.

---

# 162. Trace Payload Redaction

Span APIs must return already-redacted payloads.

Do not rely on frontend masking.

Server-side redaction is authoritative.

---

# 163. Trace Payload Limits

For example:

```text
max persisted tool response = configurable

max model input preview = configurable

max model output preview = configurable
```

If truncated:

```json
{
  "truncated": true,
  "preview": "..."
}
```

Future raw artifacts may be moved to object storage.

---

# 164. Agent Draft Validation Rules

At minimum validate:

```text
model exists

credential available if required

attached ToolVersions exist

attached KB belongs to workspace

child agents belong to workspace

guardrail versions exist

runtime limits are valid

tool-calling model capability is compatible
```

---

# 165. Workflow Validation Rules

At minimum:

```text
one START

at least one END

valid node keys

valid edge references

referenced AgentVersion exists

referenced ToolVersion exists

all nodes reachable where required

unsupported cycles rejected
```

---

# 166. Tool Validation Rules

For HTTP tools:

```text
valid URL

allowed scheme

no private/blocked host

valid input schema

valid timeout

credential belongs to workspace
```

---

# 167. Knowledge Validation Rules

Knowledge Base creation must validate:

```text
supported embedding provider

embedding dimensions

embedding model
```

Document upload validates:

```text
MIME type

file size

workspace quota if introduced
```

---

# 168. Runtime Execution Limits

If execution budget is exhausted:

Run becomes:

```text
FAILED
```

Error:

```json
{
  "code": "RUN_LIMIT_EXCEEDED",
  "message": "Agent execution exceeded its configured limit."
}
```

Trace indicates which budget was exhausted.

---

# 169. SSE Reconnection

MVP may not guarantee replay of all missed events.

If implemented, SSE `id` should support:

```text
Last-Event-ID
```

Future event persistence may allow replay.

Clients must always reconcile final state using:

```text
GET /v1/runs/{run_id}
```

after stream disconnect.

---

# 170. SSE Error Handling

Once SSE response begins, HTTP error codes can no longer represent all runtime failures.

Emit:

```text
event: run.failed
```

with normalized error payload.

Then close stream.

---

# 171. Async Operation Pattern

For operations such as document ingestion:

Create resource first.

Example:

```text
POST document
→ 202
→ document.status = UPLOADED
```

Background job updates:

```text
PROCESSING
READY
```

The API should not invent a second temporary resource unless useful.

---

# 172. Audit Events Triggered by API

Management actions should generate audit events for:

```text
agent.created

agent.updated

agent.archived

agent.version.published

tool.created

tool.version.published

credential.created

credential.rotated

credential.revoked

workflow.version.published

deployment.created

deployment.updated

api_key.created

api_key.revoked

approval.approved

approval.rejected
```

Read-only API requests do not require audit records by default.

---

# 173. API Authorization Matrix

Initial simplified matrix:

| Resource | OWNER | MEMBER |
|---|---:|---:|
| Read Agent | Yes | Yes |
| Create Agent | Yes | Yes |
| Update Agent | Yes | Yes |
| Publish Agent | Yes | Yes |
| Manage Tools | Yes | Yes |
| Manage Knowledge | Yes | Yes |
| Manage Memory | Yes | Yes |
| Run Agent | Yes | Yes |
| Evaluation | Yes | Yes |
| Deploy Agent | Yes | Yes |
| Manage Credentials | Yes | Limited/Yes initially |
| Manage Workspace | Yes | No |
| Manage Members | Yes | No |

MVP may allow broad MEMBER privileges.

Future RBAC should refine this.

---

# 174. API Grouping for Frontend

Recommended generated frontend clients:

```text
authApi

workspacesApi

agentsApi

sessionsApi

runsApi

toolsApi

credentialsApi

mcpApi

knowledgeApi

memoryApi

guardrailsApi

workflowsApi

approvalsApi

evaluationsApi

deploymentsApi

observabilityApi
```

Avoid one enormous generic API client.

---

# 175. Milestone API Availability

## M0

```text
GET /health
GET /ready
```

## M1

```text
GET /v1/me
workspaces
members
```

## M2

```text
agents
drafts
versions
```

## M3

```text
models
draft validation
```

## M4

```text
sessions
messages
runs
traces
```

## M5

```text
runs:stream
```

## M6

```text
tools
tool versions
tool test
agent tool bindings
```

## M7

```text
credentials
rotation
```

## M8

```text
MCP servers
discovery
imports
```

## M9

```text
knowledge bases
documents
search
agent KB bindings
```

## M10

```text
memory stores
memory items
memory search
```

## M11

```text
guardrails
```

## M12

```text
workflows
workflow runs
```

## M13

```text
child agent bindings
run children
```

## M14

```text
approval requests
```

## M15

```text
evaluation datasets
cases
runs
results
comparison
```

## M16

```text
deployments
API keys
public invocation
```

## M17+

```text
monitoring
audit
advanced trace APIs
```

---

# 176. Recommended FastAPI Router Layout

```text
api/
├── health.py
├── me.py
├── workspaces.py
├── agents.py
├── agent_versions.py
├── sessions.py
├── runs.py
├── tools.py
├── credentials.py
├── mcp.py
├── knowledge.py
├── memory.py
├── guardrails.py
├── workflows.py
├── approvals.py
├── evaluations.py
├── deployments.py
├── monitoring.py
└── audit.py
```

Do not create one router per database table if product resources can be grouped logically.

---

# 177. Recommended Internal Service Boundaries

Routers call application services.

Example:

```text
AgentRouter
   ↓
AgentService
   ↓
AgentRepository
```

Runtime:

```text
RunRouter
   ↓
AgentRuntimeService
   ├── ContextBuilder
   ├── ModelProviderRegistry
   ├── ToolExecutor
   ├── RetrievalService
   ├── MemoryService
   └── TraceService
```

Routers should not contain core runtime logic.

---

# 178. API Anti-Patterns

Do not:

```text
put database models directly in API responses

return ORM objects

accept raw credentials inside Agent configuration

allow public deployment callers to select AgentVersion

allow updating AgentVersion

return plaintext secrets

use 200 for failed operations

perform document embedding inside upload HTTP request

duplicate runtime logic in evaluation endpoints

put all APIs under one /actions endpoint

use different error shapes by module
```

---

# 179. MVP Endpoint Summary

Core management:

```text
/v1/me

/v1/workspaces
/v1/workspaces/{workspace_id}

/v1/agents
/v1/agents/{agent_id}
/v1/agents/{agent_id}/draft
/v1/agents/{agent_id}/versions

/v1/models

/v1/sessions
/v1/runs
/v1/traces
```

Capabilities:

```text
/v1/tools
/v1/credentials
/v1/mcp-servers
/v1/knowledge-bases
/v1/documents
/v1/memory-stores
/v1/memory-items
/v1/guardrails
/v1/workflows
/v1/approval-requests
```

Operations:

```text
/v1/evaluation-datasets
/v1/evaluation-runs

/v1/deployments
/v1/api-keys

/v1/monitoring
/v1/audit-logs
```

---

# 180. Public API Minimal Contract

A developer integrating VibesFactory should need only:

```text
Deployment ID
+
API Key
```

Invocation:

```http
POST /v1/deployments/{deployment_id}/runs
Authorization: Bearer vf_live_xxx
Content-Type: application/json
```

Body:

```json
{
  "input": {
    "type": "text",
    "text": "Hello"
  }
}
```

Response:

```json
{
  "id": "run_uuid",
  "status": "COMPLETED",
  "output": {
    "type": "text",
    "text": "Hello!"
  }
}
```

This should remain simple even if internal orchestration is complex.

---

# 181. API Stability Rules

Once an API is used by:

```text
VibesFactory Web
Public SDK
Portfolio integrations
```

avoid unnecessary breaking changes.

Safe changes:

```text
add optional response field
add endpoint
add optional query parameter
```

Breaking:

```text
rename field
remove field
change field type
change endpoint meaning
```

Breaking changes require migration strategy or new API major version.

---

# 182. OpenAPI as Executable Contract

FastAPI OpenAPI output must remain consistent with this document.

CI should eventually verify:

```text
OpenAPI generation succeeds
```

and optionally detect unintended breaking changes.

---

# 183. API Testing Requirements

Every endpoint must test:

```text
success path

authentication failure

authorization failure

validation failure

resource not found
```

where applicable.

Critical state-changing APIs must test invalid state transitions.

---

# 184. Contract Tests

Particularly important:

```text
AgentVersion cannot PATCH

Deployment cannot target another workspace's version

Tool binding cannot cross workspace

Knowledge binding cannot cross workspace

Approval cannot be resolved twice

Evaluation cannot target draft Agent

Public API cannot override AgentVersion

Credential responses never expose ciphertext/secret
```

---

# 185. E2E API Flow

The final API must support this sequence:

```text
POST workspace

POST agent

PATCH agent draft

POST agent version

POST tool

POST tool version

POST agent draft tool binding

POST knowledge base

POST document

wait READY

POST agent draft knowledge binding

POST new agent version

POST session

POST run

GET trace

POST evaluation dataset

POST evaluation cases

POST evaluation run

GET evaluation result

POST deployment

POST API key

POST public deployment run
```

This sequence should be usable entirely through API without frontend dependency.

---

# 186. Source-of-Truth Rule

When implementation and this document conflict, developers/Codex must not silently choose one.

The change must update:

```text
API.md
relevant Pydantic schemas
OpenAPI output
tests
frontend client
```

and, when architectural:

```text
ARCHITECTURE.md
DATABASE_SCHEMA.md
ERD.md
ADR
```

---

# 187. Final API Contract Principle

The management API may expose sophisticated platform concepts.

The public runtime API should remain deliberately simple.

Internally:

```text
AgentVersion
+
Session
+
Memory
+
Knowledge
+
Tools
+
MCP
+
Guardrails
+
Child Agents
+
Workflow
+
Trace
```

Externally:

```text
Input
 ↓
Deployment
 ↓
Run
 ↓
Output
```

That simplicity is a key product abstraction of VibesFactory.

## Phase 12 durable workflow contract

Workflow control-plane endpoints are workspace-scoped and publish immutable
normalized versions:

```text
POST /v1/workspaces/{workspace_id}/workflows
GET  /v1/workspaces/{workspace_id}/workflows
GET  /v1/workflows/{workflow_id}/draft
PUT  /v1/workflows/{workflow_id}/draft             (expected_revision)
POST /v1/workflows/{workflow_id}/draft:validate
GET  /v1/workflows/{workflow_id}/versions
POST /v1/workflows/{workflow_id}/versions
GET  /v1/workflow-versions/{version_id}
```

Execution is asynchronous and returns `202 Accepted`. `Idempotency-Key` is
hashed per workspace/workflow. Runs, node runs, and safe event metadata are
available from the run endpoints, including fetch-based SSE replay with
`Last-Event-ID`. Event envelopes never contain payloads or credentials;
authenticated detail endpoints provide those values on demand. Child-agent
bindings are draft-only until publish at
`/v1/agents/{agent_id}/draft/child-agents`.

`AGENT`, `TOOL`, `CONDITION`, and `TRANSFORM` expressions use a tagged AST.
Arbitrary expression strings and `eval()` are not part of the contract.
