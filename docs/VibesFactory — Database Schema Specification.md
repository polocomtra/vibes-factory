# VibesFactory — Database Schema Specification

**Document Version:** 0.1  
**Status:** Proposed / Source of Truth  
**Database:** PostgreSQL  
**Vector Extension:** pgvector  
**Related Documents:**

- BRD.md
- ARCHITECTURE.md
- IMPLEMENTATION_PLAN.md
- ERD.md

---

# 1. Purpose

This document defines the logical and physical database model for VibesFactory.

The schema is designed to support:

- Multi-workspace isolation
- Agent drafts
- Immutable agent versions
- Sessions and conversation history
- Agent runs
- Parent/child multi-agent runs
- Hierarchical traces
- Tools and tool versions
- MCP servers
- Credentials
- Knowledge bases
- Documents and vector chunks
- Long-term memory
- Guardrails
- Workflows
- Human approvals
- Evaluations
- Deployments
- Public API keys
- Monitoring
- Cost estimation
- Audit logs

The schema must support the following invariant:

```text
Mutable configuration
        ↓
Publish
        ↓
Immutable Version
        ↓
Run / Evaluate / Deploy
```

Historical executions must remain understandable even when the editable configuration later changes.

---

# 2. Core Database Principles

## 2.1 PostgreSQL Is the System of Record

PostgreSQL stores durable platform state.

Redis must never be considered the authoritative source for:

- Agents
- Versions
- Runs
- Sessions
- Workflow state
- Evaluations
- Deployments
- Credentials

Redis may contain disposable operational data.

---

## 2.2 UUIDs

All public resource identifiers use UUIDs.

Recommended PostgreSQL extension:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

Default:

```sql
gen_random_uuid()
```

Do not expose sequential integer primary keys publicly.

---

# 3. Timestamp Convention

All durable timestamps use:

```text
TIMESTAMPTZ
```

Store timestamps in UTC.

Typical columns:

```text
created_at
updated_at
started_at
completed_at
deleted_at
```

Application presentation may convert timestamps to user-local time.

---

# 4. Naming Convention

Database objects use:

```text
snake_case
```

Examples:

```text
agent_versions
workflow_node_runs
evaluation_results
```

Foreign keys use:

```text
<entity>_id
```

Example:

```text
agent_id
agent_version_id
workspace_id
```

---

# 5. Enum Strategy

Application enums should use string values.

Recommended SQLAlchemy approach:

```text
Enum(..., native_enum=False)
```

or equivalent CHECK constraints.

This avoids unnecessary migration friction when adding enum values.

Example:

```text
RUNNING
COMPLETED
FAILED
```

rather than integers such as:

```text
1
2
3
```

---

# 6. JSONB Strategy

JSONB is allowed for:

- Provider-specific settings
- Runtime configuration
- Model metadata
- Tool executor configuration
- Trace attributes
- Evaluation details
- Flexible resource metadata

JSONB should not replace relationships that need referential integrity.

Bad:

```json
{
  "tool_ids": [
    "...",
    "..."
  ]
}
```

Preferred:

```text
agent_version_tools
```

---

# 7. Workspace Isolation

Most business resources belong to:

```text
workspace_id
```

Every repository query for workspace-owned data must scope by workspace.

Example:

```sql
SELECT *
FROM agents
WHERE id = :agent_id
  AND workspace_id = :workspace_id;
```

Do not rely exclusively on frontend filtering.

Future PostgreSQL Row Level Security may be added, but application-level enforcement remains required.

---

# 8. Authentication Identity

VibesFactory maintains an application-level `users` table.

Do not tightly couple application entities to Supabase `auth.users`.

Use:

```text
external_auth_id
```

to map external identity providers to an internal VibesFactory user.

This preserves portability to another authentication provider later.

---

# 9. Users

## Table: `users`

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| external_auth_id | VARCHAR(255) | NOT NULL, UNIQUE |
| email | VARCHAR(320) | NOT NULL |
| display_name | VARCHAR(255) | NULL |
| avatar_url | TEXT | NULL |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

Indexes:

```text
UNIQUE external_auth_id
INDEX email
```

---

# 10. Workspaces

## Table: `workspaces`

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| name | VARCHAR(255) | NOT NULL |
| slug | VARCHAR(100) | NOT NULL |
| owner_user_id | UUID | FK users |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

Constraint:

```text
UNIQUE(owner_user_id, slug)
```

---

# 11. Workspace Members

## Table: `workspace_members`

| Column | Type | Constraints |
|---|---|---|
| workspace_id | UUID | FK workspaces |
| user_id | UUID | FK users |
| role | VARCHAR(32) | OWNER / MEMBER |
| created_at | TIMESTAMPTZ | NOT NULL |

Primary key:

```text
(workspace_id, user_id)
```

Indexes:

```text
INDEX user_id
```

Deletion:

```text
workspace deleted
→ cascade workspace_members
```

---

# 12. Agents

The `agents` table represents the durable identity of an agent.

It does not contain the deployed configuration.

## Table: `agents`

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| workspace_id | UUID | FK workspaces |
| name | VARCHAR(255) | NOT NULL |
| slug | VARCHAR(100) | NOT NULL |
| description | TEXT | NULL |
| status | VARCHAR(32) | ACTIVE / ARCHIVED |
| latest_version_number | INTEGER | NOT NULL DEFAULT 0 |
| created_by | UUID | FK users |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |
| archived_at | TIMESTAMPTZ | NULL |

Constraint:

```text
UNIQUE(workspace_id, slug)
```

Indexes:

```text
INDEX workspace_id
INDEX(workspace_id, status)
```

---

# 13. Agent Drafts

An Agent has one current editable draft.

## Table: `agent_drafts`

| Column | Type | Constraints |
|---|---|---|
| agent_id | UUID | PK, FK agents |
| instructions | TEXT | NOT NULL |
| model_provider | VARCHAR(64) | NOT NULL |
| model_name | VARCHAR(255) | NOT NULL |
| model_config | JSONB | NOT NULL DEFAULT '{}' |
| runtime_config | JSONB | NOT NULL DEFAULT '{}' |
| memory_config | JSONB | NOT NULL DEFAULT '{}' |
| updated_by | UUID | FK users |
| updated_at | TIMESTAMPTZ | NOT NULL |

Example `model_config`:

```json
{
  "temperature": 0.2,
  "max_output_tokens": 4096
}
```

Example `runtime_config`:

```json
{
  "max_steps": 20,
  "max_model_calls": 10,
  "max_tool_calls": 10,
  "max_child_runs": 5,
  "max_agent_depth": 3,
  "max_total_tokens": 100000,
  "timeout_seconds": 120
}
```

---

# 14. Agent Versions

Agent versions are immutable published snapshots.

## Table: `agent_versions`

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| workspace_id | UUID | FK workspaces |
| agent_id | UUID | FK agents |
| version_number | INTEGER | NOT NULL |
| instructions | TEXT | NOT NULL |
| model_provider | VARCHAR(64) | NOT NULL |
| model_name | VARCHAR(255) | NOT NULL |
| model_config | JSONB | NOT NULL |
| runtime_config | JSONB | NOT NULL |
| memory_config | JSONB | NOT NULL |
| snapshot | JSONB | NOT NULL |
| change_note | TEXT | NULL |
| created_by | UUID | FK users |
| created_at | TIMESTAMPTZ | NOT NULL |

Constraints:

```text
UNIQUE(agent_id, version_number)
```

Indexes:

```text
INDEX agent_id
INDEX(workspace_id, agent_id)
```

`agent_versions` must never be updated after creation.

The application service must prohibit:

```text
UPDATE agent_versions ...
```

for business configuration.

---

# 15. Agent Draft Tool Bindings

## Table: `agent_draft_tools`

| Column | Type | Constraints |
|---|---|---|
| agent_id | UUID | FK agents |
| tool_version_id | UUID | FK tool_versions |
| enabled | BOOLEAN | NOT NULL DEFAULT TRUE |
| alias | VARCHAR(255) | NULL |
| configuration | JSONB | NOT NULL DEFAULT '{}' |
| created_at | TIMESTAMPTZ | NOT NULL |

Primary key:

```text
(agent_id, tool_version_id)
```

---

# 16. Agent Version Tool Bindings

## Table: `agent_version_tools`

| Column | Type | Constraints |
|---|---|---|
| agent_version_id | UUID | FK agent_versions |
| tool_version_id | UUID | FK tool_versions |
| alias | VARCHAR(255) | NULL |
| configuration | JSONB | NOT NULL DEFAULT '{}' |
| created_at | TIMESTAMPTZ | NOT NULL |

Primary key:

```text
(agent_version_id, tool_version_id)
```

Published agent versions reference immutable tool versions.

---

# 17. Knowledge Bindings

## Table: `agent_draft_knowledge_bases`

| Column | Type |
|---|---|
| agent_id | UUID |
| knowledge_base_id | UUID |
| retrieval_config | JSONB |
| created_at | TIMESTAMPTZ |

Primary key:

```text
(agent_id, knowledge_base_id)
```

## Table: `agent_version_knowledge_bases`

| Column | Type |
|---|---|
| agent_version_id | UUID |
| knowledge_base_id | UUID |
| retrieval_config | JSONB |
| created_at | TIMESTAMPTZ |

Primary key:

```text
(agent_version_id, knowledge_base_id)
```

MVP note:

Knowledge documents themselves remain mutable.

AgentVersion freezes the retrieval configuration, not every underlying document.

Historical traces preserve actual chunk IDs retrieved during execution.

Future versions may implement KnowledgeBase snapshots.

---

# 18. Child Agent Bindings

## Table: `agent_draft_child_agents`

| Column | Type |
|---|---|
| agent_id | UUID |
| child_agent_id | UUID |
| alias | VARCHAR(255) |
| description_override | TEXT |
| created_at | TIMESTAMPTZ |

Primary key:

```text
(agent_id, child_agent_id)
```

## Table: `agent_version_child_agents`

| Column | Type |
|---|---|
| agent_version_id | UUID |
| child_agent_id | UUID |
| child_agent_version_id | UUID NULL |
| alias | VARCHAR(255) |
| description_override | TEXT |
| created_at | TIMESTAMPTZ |

If `child_agent_version_id` is provided, runtime invokes that exact version.

For production reproducibility, published agent versions should preferably pin child agent versions.

---

# 19. Sessions

## Table: `sessions`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| agent_id | UUID |
| user_id | UUID |
| title | VARCHAR(255) NULL |
| metadata | JSONB |
| created_at | TIMESTAMPTZ |
| last_activity_at | TIMESTAMPTZ |
| expires_at | TIMESTAMPTZ NULL |

Primary key:

```text
id
```

Indexes:

```text
INDEX(workspace_id, user_id, last_activity_at DESC)
INDEX(agent_id, last_activity_at DESC)
```

Session belongs to the logical Agent rather than a specific version.

Each Run records which AgentVersion actually handled a turn.

---

# 20. Messages

## Table: `messages`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| session_id | UUID |
| run_id | UUID NULL |
| role | VARCHAR(32) |
| sequence_no | INTEGER |
| content | JSONB |
| token_count | INTEGER NULL |
| metadata | JSONB |
| created_at | TIMESTAMPTZ |

Roles:

```text
USER
ASSISTANT
SYSTEM
TOOL
```

Constraint:

```text
UNIQUE(session_id, sequence_no)
```

Indexes:

```text
INDEX(session_id, sequence_no)
INDEX run_id
```

Recommended normalized `content`:

```json
{
  "type": "text",
  "text": "Hello"
}
```

Future multimodal:

```json
{
  "parts": [
    {
      "type": "text",
      "text": "Analyze this"
    },
    {
      "type": "image",
      "storage_uri": "..."
    }
  ]
}
```

---

# 21. Runs

Every agent execution produces one Run.

## Table: `runs`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| agent_id | UUID |
| agent_version_id | UUID |
| deployment_id | UUID NULL |
| session_id | UUID NULL |
| trace_id | UUID |
| parent_run_id | UUID NULL |
| root_run_id | UUID |
| workflow_run_id | UUID NULL |
| status | VARCHAR(32) |
| input | JSONB |
| output | JSONB NULL |
| error_code | VARCHAR(100) NULL |
| error_message | TEXT NULL |
| execution_budget | JSONB |
| usage | JSONB |
| estimated_cost | NUMERIC(18,8) NULL |
| started_at | TIMESTAMPTZ |
| completed_at | TIMESTAMPTZ NULL |
| created_at | TIMESTAMPTZ |

Status:

```text
QUEUED
RUNNING
WAITING_TOOL
WAITING_APPROVAL
COMPLETED
FAILED
CANCELLED
```

Indexes:

```text
INDEX(workspace_id, created_at DESC)
INDEX(agent_id, created_at DESC)
INDEX(agent_version_id, created_at DESC)
INDEX(session_id, created_at)
INDEX(parent_run_id)
INDEX(root_run_id)
INDEX(status, created_at)
```

Invariant:

```text
agent_version_id IS NOT NULL
```

for every real agent runtime execution.

---

# 22. Parent / Child Run Rules

Root run:

```text
parent_run_id = NULL
root_run_id = id
```

Child run:

```text
parent_run_id = parent.id
root_run_id = parent.root_run_id
```

This supports:

```text
Supervisor
├── Research Agent
└── Writer Agent
```

without mixing child execution into one Run row.

---

# 23. Traces

## Table: `traces`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| root_run_id | UUID NULL |
| workflow_run_id | UUID NULL |
| status | VARCHAR(32) |
| started_at | TIMESTAMPTZ |
| completed_at | TIMESTAMPTZ NULL |
| attributes | JSONB |

Indexes:

```text
INDEX workspace_id
INDEX root_run_id
```

---

# 24. Spans

## Table: `spans`

| Column | Type |
|---|---|
| id | UUID |
| trace_id | UUID |
| parent_span_id | UUID NULL |
| run_id | UUID NULL |
| workflow_run_id | UUID NULL |
| span_type | VARCHAR(64) |
| name | VARCHAR(255) |
| status | VARCHAR(32) |
| input | JSONB NULL |
| output | JSONB NULL |
| usage | JSONB |
| error | JSONB NULL |
| attributes | JSONB |
| started_at | TIMESTAMPTZ |
| completed_at | TIMESTAMPTZ NULL |

Span types:

```text
RUN
CONTEXT_BUILD
MODEL
TOOL
RETRIEVAL
MEMORY_RETRIEVAL
MEMORY_WRITE
GUARDRAIL
WORKFLOW_NODE
CHILD_AGENT
```

Indexes:

```text
INDEX(trace_id, started_at)
INDEX(parent_span_id)
INDEX(run_id, started_at)
INDEX(span_type, started_at)
```

Phase 4 creates `sessions`, `messages`, `runs`, `traces`, and `spans` in
migration `0004_runtime_vertical_slice` and adds per-span usage in
`0005_span_usage_breakdown`. The initial runtime persists one root `RUN` span,
one `CONTEXT_BUILD` span, and one child `MODEL` span per synchronous
execution. Provider credentials are never persisted in these tables;
`estimated_cost` remains nullable until model pricing is implemented.

Large payload policy:

Do not store unlimited tool or model payloads.

Application must apply configurable truncation.

Future large trace payloads may be stored in object storage.

---

# 25. Tools

## Table: `tools`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| name | VARCHAR(255) |
| slug | VARCHAR(100) |
| description | TEXT |
| tool_type | VARCHAR(32) |
| status | VARCHAR(32) |
| latest_version_number | INTEGER |
| created_by | UUID |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

Tool types:

```text
FUNCTION
HTTP
MCP
AGENT
WORKFLOW
```

Constraint:

```text
UNIQUE(workspace_id, slug)
```

---

# 26. Tool Versions

## Table: `tool_versions`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| tool_id | UUID |
| version_number | INTEGER |
| name | VARCHAR(255) |
| description | TEXT |
| input_schema | JSONB |
| output_schema | JSONB NULL |
| executor_type | VARCHAR(32) |
| executor_config | JSONB |
| timeout_seconds | INTEGER |
| retry_policy | JSONB |
| risk_level | VARCHAR(16) |
| side_effect | BOOLEAN |
| idempotent | BOOLEAN |
| created_by | UUID |
| created_at | TIMESTAMPTZ |

Risk:

```text
LOW
MEDIUM
HIGH
```

Constraint:

```text
UNIQUE(tool_id, version_number)
```

Tool versions are immutable after publication.

---

# 27. Credentials

## Table: `credentials`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| name | VARCHAR(255) |
| provider | VARCHAR(100) |
| credential_type | VARCHAR(64) |
| ciphertext | BYTEA |
| key_version | VARCHAR(100) |
| metadata | JSONB |
| created_by | UUID |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |
| revoked_at | TIMESTAMPTZ NULL |

Never store:

```text
plaintext secret
raw API key
access token
refresh token
```

outside encrypted storage.

Credential values must never be returned through ordinary GET APIs.

Migration `0009_credential_vault` creates this table. `ciphertext` contains the
nonce-bearing AES-GCM payload; `key_version` identifies the active encryption key
version. `revoked_at` is a soft-revocation marker and must be checked before
decryption or executor use.

---

# 28. MCP Servers

## Table: `mcp_servers`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| name | VARCHAR(255) |
| transport | VARCHAR(32) |
| endpoint | TEXT |
| credential_id | UUID NULL |
| status | VARCHAR(32) |
| configuration | JSONB |
| last_discovered_at | TIMESTAMPTZ NULL |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

Transport examples:

```text
STREAMABLE_HTTP
STDIO_LOCAL
```

Hosted production environment should normally use network-capable transports.

---

# 29. MCP Tool Catalog

Optional but recommended.

## Table: `mcp_tool_catalog`

| Column | Type |
|---|---|
| id | UUID |
| mcp_server_id | UUID |
| remote_name | VARCHAR(255) |
| description | TEXT |
| input_schema | JSONB |
| discovered_at | TIMESTAMPTZ |
| metadata | JSONB |

Constraint:

```text
UNIQUE(mcp_server_id, remote_name)
```

This table is a cache/catalog.

The authoritative remote MCP server may change independently.

---

# 30. Knowledge Bases

## Table: `knowledge_bases`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| name | VARCHAR(255) |
| description | TEXT NULL |
| embedding_provider | VARCHAR(64) |
| embedding_model | VARCHAR(255) |
| embedding_dimensions | INTEGER |
| status | VARCHAR(32) |
| metadata | JSONB |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

Status:

```text
ACTIVE
ARCHIVED
```

---

# 31. Documents

## Table: `documents`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| knowledge_base_id | UUID |
| name | VARCHAR(500) |
| mime_type | VARCHAR(255) |
| storage_uri | TEXT |
| checksum | VARCHAR(128) NULL |
| size_bytes | BIGINT |
| status | VARCHAR(32) |
| error_code | VARCHAR(100) NULL |
| error_message | TEXT NULL |
| metadata | JSONB |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

Status:

```text
UPLOADED
PROCESSING
READY
FAILED
DELETED
```

Indexes:

```text
INDEX(knowledge_base_id, status)
INDEX(workspace_id, created_at DESC)
```

---

# 32. Document Chunks

Requires pgvector.

Example:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## Table: `document_chunks`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| knowledge_base_id | UUID |
| document_id | UUID |
| chunk_index | INTEGER |
| content | TEXT |
| embedding | VECTOR(n) |
| token_count | INTEGER |
| page_number | INTEGER NULL |
| section | VARCHAR(500) NULL |
| metadata | JSONB |
| created_at | TIMESTAMPTZ |

Constraint:

```text
UNIQUE(document_id, chunk_index)
```

Indexes:

```text
INDEX(document_id, chunk_index)
INDEX knowledge_base_id
VECTOR INDEX embedding
```

Vector dimension must match `knowledge_bases.embedding_dimensions`.

Changing embedding dimensions requires re-indexing the knowledge base.

---

# 33. Retrieval Provenance

Do not create a database row for every retrieval unless needed.

Retrieved chunks should be recorded in the relevant Trace Span output/attributes:

```json
{
  "knowledge_base_id": "...",
  "chunks": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "score": 0.87,
      "page_number": 12
    }
  ]
}
```

This preserves historical provenance.

---

# 34. Memory Stores

## Table: `memory_stores`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| name | VARCHAR(255) |
| description | TEXT NULL |
| embedding_provider | VARCHAR(64) |
| embedding_model | VARCHAR(255) |
| embedding_dimensions | INTEGER |
| configuration | JSONB |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

---

# 35. Memory Items

## Table: `memory_items`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| memory_store_id | UUID |
| user_id | UUID NULL |
| agent_id | UUID NULL |
| memory_type | VARCHAR(32) |
| content | TEXT |
| embedding | VECTOR(n) NULL |
| importance | NUMERIC(4,3) NULL |
| confidence | NUMERIC(4,3) NULL |
| source_session_id | UUID NULL |
| source_run_id | UUID NULL |
| metadata | JSONB |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |
| expires_at | TIMESTAMPTZ NULL |
| deleted_at | TIMESTAMPTZ NULL |

Types:

```text
PROFILE
SEMANTIC
SUMMARY
PROCEDURAL
```

Indexes:

```text
INDEX(memory_store_id, user_id)
INDEX(memory_store_id, agent_id)
INDEX(expires_at)
VECTOR INDEX embedding
```

Scope invariant:

At least one meaningful scope must exist.

Typical user memory:

```text
user_id != NULL
```

Agent-global procedural memory may use:

```text
agent_id != NULL
user_id = NULL
```

---

# 36. Guardrail Policies

Guardrails require versioned configuration for reproducible deployed agents.

## Table: `guardrail_policies`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| name | VARCHAR(255) |
| description | TEXT |
| latest_version_number | INTEGER |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

---

# 37. Guardrail Versions

## Table: `guardrail_versions`

| Column | Type |
|---|---|
| id | UUID |
| guardrail_policy_id | UUID |
| version_number | INTEGER |
| guardrail_type | VARCHAR(64) |
| configuration | JSONB |
| created_by | UUID |
| created_at | TIMESTAMPTZ |

Constraint:

```text
UNIQUE(guardrail_policy_id, version_number)
```

---

# 38. Agent Guardrail Bindings

## Table: `agent_draft_guardrails`

```text
agent_id
guardrail_version_id
hook
priority
```

## Table: `agent_version_guardrails`

```text
agent_version_id
guardrail_version_id
hook
priority
```

Hooks:

```text
INPUT
MODEL_OUTPUT
TOOL_INPUT
TOOL_OUTPUT
```

Primary key may include:

```text
(agent_version_id, guardrail_version_id, hook)
```

---

# 39. Workflows

## Table: `workflows`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| name | VARCHAR(255) |
| slug | VARCHAR(100) |
| description | TEXT |
| latest_version_number | INTEGER |
| status | VARCHAR(32) |
| created_by | UUID |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

Constraint:

```text
UNIQUE(workspace_id, slug)
```

---

# 40. Workflow Drafts

## Table: `workflow_drafts`

| Column | Type |
|---|---|
| workflow_id | UUID |
| definition | JSONB |
| updated_by | UUID |
| updated_at | TIMESTAMPTZ |

The draft definition may contain editable graph nodes and edges.

At publication time, it is normalized into immutable workflow version tables.

---

# 41. Workflow Versions

## Table: `workflow_versions`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| workflow_id | UUID |
| version_number | INTEGER |
| configuration | JSONB |
| created_by | UUID |
| created_at | TIMESTAMPTZ |

Constraint:

```text
UNIQUE(workflow_id, version_number)
```

Immutable after creation.

---

# 42. Workflow Nodes

## Table: `workflow_nodes`

| Column | Type |
|---|---|
| id | UUID |
| workflow_version_id | UUID |
| node_key | VARCHAR(100) |
| node_type | VARCHAR(32) |
| name | VARCHAR(255) |
| configuration | JSONB |
| position | JSONB NULL |
| created_at | TIMESTAMPTZ |

Node types:

```text
START
END
AGENT
TOOL
CONDITION
TRANSFORM
PARALLEL
APPROVAL
```

Constraint:

```text
UNIQUE(workflow_version_id, node_key)
```

---

# 43. Workflow Edges

## Table: `workflow_edges`

| Column | Type |
|---|---|
| id | UUID |
| workflow_version_id | UUID |
| source_node_id | UUID |
| target_node_id | UUID |
| condition | JSONB NULL |
| priority | INTEGER DEFAULT 0 |
| created_at | TIMESTAMPTZ |

Indexes:

```text
INDEX source_node_id
INDEX target_node_id
```

---

# 44. Workflow Runs

## Table: `workflow_runs`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| workflow_id | UUID |
| workflow_version_id | UUID |
| trace_id | UUID |
| status | VARCHAR(32) |
| input | JSONB |
| output | JSONB NULL |
| variables | JSONB |
| waiting_reason | VARCHAR(100) NULL |
| error_code | VARCHAR(100) NULL |
| error_message | TEXT NULL |
| started_at | TIMESTAMPTZ |
| completed_at | TIMESTAMPTZ NULL |

Statuses:

```text
QUEUED
RUNNING
WAITING_APPROVAL
COMPLETED
FAILED
CANCELLED
```

---

# 45. Workflow Node Runs

## Table: `workflow_node_runs`

| Column | Type |
|---|---|
| id | UUID |
| workflow_run_id | UUID |
| workflow_node_id | UUID |
| attempt | INTEGER |
| status | VARCHAR(32) |
| input | JSONB |
| output | JSONB NULL |
| error | JSONB NULL |
| agent_run_id | UUID NULL |
| started_at | TIMESTAMPTZ |
| completed_at | TIMESTAMPTZ NULL |

Constraint:

```text
UNIQUE(workflow_run_id, workflow_node_id, attempt)
```

---

# 46. Human Approval Requests

## Table: `approval_requests`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| run_id | UUID NULL |
| workflow_run_id | UUID NULL |
| workflow_node_run_id | UUID NULL |
| tool_version_id | UUID NULL |
| status | VARCHAR(32) |
| requested_action | VARCHAR(255) |
| arguments | JSONB |
| risk_reason | TEXT NULL |
| requested_at | TIMESTAMPTZ |
| expires_at | TIMESTAMPTZ NULL |
| resolved_at | TIMESTAMPTZ NULL |
| resolved_by | UUID NULL |
| resolution_comment | TEXT NULL |

Status:

```text
PENDING
APPROVED
REJECTED
EXPIRED
```

Important invariant:

`arguments` stores the exact approved pending action.

Runtime must not ask the model to recreate arguments after approval.

---

# 47. Evaluation Datasets

## Table: `evaluation_datasets`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| name | VARCHAR(255) |
| description | TEXT |
| created_by | UUID |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

---

# 48. Evaluation Cases

## Table: `evaluation_cases`

| Column | Type |
|---|---|
| id | UUID |
| evaluation_dataset_id | UUID |
| position | INTEGER |
| input | JSONB |
| expected_output | JSONB NULL |
| expected_tool | VARCHAR(255) NULL |
| expected_schema | JSONB NULL |
| rubric | TEXT NULL |
| metadata | JSONB |
| created_at | TIMESTAMPTZ |

Constraint:

```text
UNIQUE(evaluation_dataset_id, position)
```

---

# 49. Evaluation Runs

## Table: `evaluation_runs`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| evaluation_dataset_id | UUID |
| agent_id | UUID |
| agent_version_id | UUID |
| status | VARCHAR(32) |
| aggregate_metrics | JSONB |
| started_at | TIMESTAMPTZ |
| completed_at | TIMESTAMPTZ NULL |
| created_by | UUID |
| created_at | TIMESTAMPTZ |

Status:

```text
QUEUED
RUNNING
COMPLETED
FAILED
CANCELLED
```

Invariant:

```text
agent_version_id
```

is mandatory.

Evaluation never runs against mutable drafts.

---

# 50. Evaluation Results

One case may produce multiple evaluator results.

## Table: `evaluation_results`

| Column | Type |
|---|---|
| id | UUID |
| evaluation_run_id | UUID |
| evaluation_case_id | UUID |
| run_id | UUID |
| evaluator_type | VARCHAR(100) |
| score | NUMERIC(8,5) NULL |
| passed | BOOLEAN NULL |
| details | JSONB |
| created_at | TIMESTAMPTZ |

Indexes:

```text
INDEX(evaluation_run_id, evaluation_case_id)
INDEX run_id
```

Examples:

```text
EXACT_MATCH
CONTAINS
TOOL_CALL
JSON_SCHEMA
LATENCY
LLM_JUDGE
GROUNDEDNESS
```

---

# 51. Deployments

## Table: `deployments`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| agent_id | UUID |
| agent_version_id | UUID |
| name | VARCHAR(255) |
| slug | VARCHAR(100) |
| environment | VARCHAR(32) |
| status | VARCHAR(32) |
| configuration | JSONB |
| created_by | UUID |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

Environment:

```text
DEVELOPMENT
STAGING
PRODUCTION
```

Status:

```text
ACTIVE
DISABLED
```

Constraint:

```text
UNIQUE(workspace_id, slug)
```

Deployment rollback is:

```text
UPDATE deployments
SET agent_version_id = previous_version_id
```

No AgentVersion mutation occurs.

---

# 52. Public API Keys

## Table: `api_keys`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| deployment_id | UUID NULL |
| name | VARCHAR(255) |
| key_prefix | VARCHAR(32) |
| key_hash | VARCHAR(255) |
| created_by | UUID |
| created_at | TIMESTAMPTZ |
| last_used_at | TIMESTAMPTZ NULL |
| expires_at | TIMESTAMPTZ NULL |
| revoked_at | TIMESTAMPTZ NULL |

Never persist the original API key.

Creation flow:

```text
generate raw key
↓
show once
↓
hash
↓
store hash
```

---

# 53. Pricing Registry

## Table: `model_pricing`

| Column | Type |
|---|---|
| id | UUID |
| provider | VARCHAR(64) |
| model | VARCHAR(255) |
| effective_from | TIMESTAMPTZ |
| effective_to | TIMESTAMPTZ NULL |
| input_price_per_million | NUMERIC(18,8) |
| output_price_per_million | NUMERIC(18,8) |
| cached_input_price_per_million | NUMERIC(18,8) NULL |
| metadata | JSONB |

Constraint:

```text
UNIQUE(provider, model, effective_from)
```

Costs stored on Runs are estimates.

They must not be presented as authoritative provider billing.

---

# 54. Audit Logs

## Table: `audit_logs`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID |
| actor_user_id | UUID NULL |
| actor_type | VARCHAR(32) |
| action | VARCHAR(255) |
| resource_type | VARCHAR(100) |
| resource_id | UUID NULL |
| metadata | JSONB |
| created_at | TIMESTAMPTZ |

Examples:

```text
agent.created
agent.version.published
tool.created
credential.created
deployment.updated
approval.approved
approval.rejected
```

Indexes:

```text
INDEX(workspace_id, created_at DESC)
INDEX(resource_type, resource_id)
INDEX(actor_user_id, created_at DESC)
```

---

# 55. Optional Job Records

Recommended once asynchronous infrastructure is introduced.

## Table: `jobs`

| Column | Type |
|---|---|
| id | UUID |
| workspace_id | UUID NULL |
| job_type | VARCHAR(100) |
| status | VARCHAR(32) |
| idempotency_key | VARCHAR(255) NULL |
| payload | JSONB |
| result | JSONB NULL |
| error | JSONB NULL |
| attempt_count | INTEGER |
| created_at | TIMESTAMPTZ |
| started_at | TIMESTAMPTZ NULL |
| completed_at | TIMESTAMPTZ NULL |

Constraint:

```text
UNIQUE(job_type, idempotency_key)
```

where `idempotency_key` is not null.

Suitable for:

```text
DOCUMENT_INGESTION
MEMORY_EXTRACTION
EVALUATION_BATCH
```

The queue itself remains outside PostgreSQL.

---

# 56. Deletion Rules

Hard deletion should be conservative.

Recommended behavior:

```text
Workspace
→ destructive operation
→ cascade workspace-owned resources only after explicit confirmation
```

Agent deletion:

```text
prefer archive
```

rather than immediate hard delete when:

```text
runs
deployments
evaluations
```

reference it.

Published versions should normally not be deleted if execution history references them.

Knowledge documents may use logical status:

```text
DELETED
```

before physical cleanup.

Credential revocation should set:

```text
revoked_at
```

rather than deleting immediately.

---

# 57. Foreign-Key Deletion Strategy

Use `ON DELETE CASCADE` only for obvious ownership relationships such as:

```text
workspace
→ workspace_members

knowledge_base
→ document
→ document_chunks

evaluation_dataset
→ evaluation_cases
```

Use `RESTRICT` or default behavior for historical resources such as:

```text
agent_version
← run

tool_version
← agent_version_tools

workflow_version
← workflow_run
```

Historical execution must not silently disappear.

---

# 58. Immutability Enforcement

Application services must prohibit modification of:

```text
agent_versions
tool_versions
guardrail_versions
workflow_versions
workflow_nodes belonging to published versions
workflow_edges belonging to published versions
```

Database permissions may later provide additional protection.

Tests must explicitly verify immutability.

---

# 59. Workspace Integrity

Where practical, duplicate `workspace_id` onto high-volume child entities such as:

```text
runs
messages
document_chunks
memory_items
```

even when it can be derived through joins.

Benefits:

```text
tenant filtering
index locality
security validation
operational queries
```

Application creation logic must ensure the workspace IDs agree with parent resources.

---

# 60. Recommended Core Indexes

Critical operational indexes:

```text
agents(workspace_id, status)

agent_versions(agent_id, version_number)

sessions(workspace_id, user_id, last_activity_at DESC)

messages(session_id, sequence_no)

runs(workspace_id, created_at DESC)

runs(agent_id, created_at DESC)

runs(agent_version_id, created_at DESC)

runs(root_run_id)

spans(trace_id, started_at)

spans(run_id, started_at)

documents(knowledge_base_id, status)

document_chunks(knowledge_base_id)

memory_items(memory_store_id, user_id)

workflow_node_runs(workflow_run_id)

evaluation_results(evaluation_run_id)

audit_logs(workspace_id, created_at DESC)
```

---

# 61. Vector Index Strategy

During early development with small datasets:

```text
exact vector search
```

is acceptable.

Once data grows, add approximate indexing such as:

```text
HNSW
```

when supported by the deployed pgvector version.

Do not tune ANN indexing before representative data exists.

Separate indexes should exist for:

```text
document_chunks.embedding

memory_items.embedding
```

because they serve different retrieval domains.

---

# 62. Connection Pooling

Cloud Run may scale horizontally.

Therefore database connection pools must remain conservative.

Example initial application pool:

```text
pool_size = 5
max_overflow = 2
```

With:

```text
max Cloud Run instances = 2
```

upper application connection pressure remains bounded.

Production configuration must consider the actual Supabase/PostgreSQL connection limits.

---

# 63. Migration Order

Recommended Alembic migration sequence:

```text
001 extensions

002 users_workspaces

003 agents_agent_drafts_agent_versions

004 sessions_messages

005 traces_runs_spans

006 tools_tool_versions

007 credentials

008 mcp

009 knowledge_documents_chunks

010 memory

011 guardrails

012 workflows

013 approvals

014 evaluations

015 deployments_api_keys

016 pricing

017 audit_logs

018 jobs
```

Binding tables may be created together with their owning domain.

---

# 64. Transaction Boundaries

Publishing AgentVersion should occur in one transaction:

```text
lock agent
↓
read draft
↓
increment version number
↓
create agent_version
↓
copy tool bindings
↓
copy knowledge bindings
↓
copy guardrail bindings
↓
copy child-agent bindings
↓
update latest_version_number
↓
commit
```

Failure must not produce a partially published version.

---

# 65. Run Creation Transaction

Recommended:

```text
resolve agent_version
↓
create trace
↓
create run
↓
create root span
↓
commit
↓
begin runtime execution
```

This ensures failed execution can still be observed.

---

# 66. Run Completion Transaction

At completion:

```text
persist assistant message

update run output

update usage

update estimated cost

mark COMPLETED

close root span

close trace
```

These operations should be coordinated so run status and persisted output do not contradict each other.

---

# 67. Evaluation Transaction Rules

Each test case creates an ordinary Run.

Evaluation-specific results reference the Run.

Never store only an evaluation score without preserving the underlying execution.

This enables:

```text
evaluation result
↓
open actual trace
↓
debug failure
```

---

# 68. Workflow / Agent Relationship

Agent runs may belong to:

```text
workflow_run_id
```

Workflow node execution stores:

```text
agent_run_id
```

This gives bidirectional debugging:

```text
Workflow Run
→ Node
→ Agent Run
→ Trace
```

---

# 69. Trace and Audit Separation

Do not combine these tables.

Trace:

```text
technical execution
```

Audit log:

```text
user/platform governance action
```

Example:

```text
tool execution
→ span

tool definition edited
→ audit_log
```

---

# 70. Data Retention

MVP may keep operational data indefinitely.

Architecture must allow future policies for:

```text
messages
runs
spans
audit logs
memory items
uploaded files
```

Do not build automatic deletion until policy requirements are defined.

---

# 71. Sensitive Data Rules

Never persist secrets into:

```text
messages

runs.input

runs.output

spans.input

spans.output

audit_logs.metadata
```

without centralized redaction.

Sensitive telemetry handling must occur before database writes.

---

# 72. Seed Data

Development seed should create:

```text
demo user

demo workspace

demo agent

demo agent draft

demo fake model configuration

calculator tool

tool version

sample evaluation dataset
```

Do not insert real provider keys.

---

# 73. Database Test Requirements

Integration tests must verify:

```text
workspace isolation

foreign-key integrity

version immutability

agent version publication transaction

run parent/root relationships

session message ordering

tool version bindings

knowledge chunk retrieval

memory scoping

workflow run persistence

evaluation-to-run linkage

deployment-to-version linkage
```

---

# 74. Important Schema Invariants

These invariants must remain true throughout implementation.

### Invariant A

```text
Run
→ AgentVersion
```

always.

Never:

```text
Run
→ Agent Draft
```

---

### Invariant B

```text
Deployment
→ AgentVersion
```

always.

---

### Invariant C

AgentVersion configuration is immutable.

---

### Invariant D

Tool bindings on AgentVersion resolve to immutable ToolVersion.

---

### Invariant E

EvaluationRun references a fixed AgentVersion.

---

### Invariant F

Long-term Memory is separate from Session messages.

---

### Invariant G

Workflow state is separate from Memory and Session.

---

### Invariant H

Every child agent execution creates another Run.

---

### Invariant I

Trace hierarchy uses:

```text
trace_id
parent_span_id
```

not nested JSON-only storage.

---

### Invariant J

Credentials are encrypted and never embedded inside agent configuration.

---

# 75. Future Schema Extensions

Post-MVP additions may include:

```text
organizations

fine-grained RBAC

agent registry

A2A endpoints

connector definitions

OAuth token lifecycle

knowledge base versions

prompt template registry

online evaluation samples

simulation personas

hosted agent artifacts

runtime pools

billing usage

subscription plans
```

These should not block MVP implementation.

---

# 76. Definition of Done for Database Layer

The database layer is considered implementation-ready when:

```text
all MVP tables have SQLAlchemy models

all foreign keys are defined

all major constraints exist

required indexes exist

Alembic migrations run from empty database

Alembic migrations upgrade existing development database

repositories enforce workspace scope

published resources are immutable

pgvector retrieval works

integration tests validate core relationships
```

---

# 77. Coding Agent Instruction

Codex must not infer a substantially different persistence model without explicitly documenting the architectural change.

When implementing a milestone:

```text
use this document for entity names

use this document for relationship direction

use this document for immutability rules

use this document for workspace scoping

use this document for deletion behavior

use this document for historical execution guarantees
```

If implementation requires changing this schema, update:

```text
DATABASE_SCHEMA.md
ERD.md
relevant ADR
Alembic migration
tests
```

in the same change.
