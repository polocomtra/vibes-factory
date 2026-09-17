# VibesFactory — Implementation Plan

**Document Version:** 0.1  
**Project:** VibesFactory  
**Document Type:** Engineering Implementation Plan  
**Related Documents:**

- Business Requirements Document
- System Architecture
- Future: Database ERD
- Future: API Specification

---

# 1. Purpose

This document defines the implementation sequence for VibesFactory.

VibesFactory is a production-inspired Agentic AI Platform providing:

- Agent creation
- Model configuration
- Instructions
- Sessions
- Knowledge and RAG
- Memory
- Tools
- MCP
- Guardrails
- Workflows
- Multi-agent orchestration
- Tracing
- Monitoring
- Evaluation
- Versioning
- Deployment
- Public agent APIs

This implementation plan is intended to be sufficiently specific that a coding agent such as Codex can execute the project incrementally while preserving architectural consistency.

The primary objective is:

> Build a working vertical agent platform first, then progressively add platform capabilities around the runtime.

---

# 2. Implementation Philosophy

The implementation shall follow six rules.

## Rule 1 — Vertical Slices Before Breadth

Do not build all database models first, then all APIs, then all UI.

Instead build complete slices.

Example:

```text
Create Agent
    ↓
Save Agent
    ↓
Publish Version
    ↓
Invoke Runtime
    ↓
Call LLM
    ↓
Persist Run
    ↓
View Trace
```

This entire lifecycle should work before adding RAG.

---

## Rule 2 — Runtime Is the Product Core

The project is not primarily a CRUD application.

Priority order:

```text
Runtime correctness
    >
Tracing
    >
Agent lifecycle
    >
Tools
    >
RAG
    >
Memory
    >
Workflow
    >
UI polish
```

---

## Rule 3 — Domain Before Framework

Do not allow:

```text
LangChain
LangGraph
OpenAI SDK
Google SDK
```

to become the platform domain model.

All external frameworks must live behind adapters.

---

## Rule 4 — Production-Like, Not Production-Scale

Implement:

```text
versioning
tracing
timeouts
permissions
evaluations
security boundaries
```

Do not initially implement:

```text
Kubernetes
multi-region
hundreds of connectors
enterprise RBAC
distributed microservices
```

---

## Rule 5 — Every Phase Must Remain Deployable

At the end of each milestone:

```text
main branch
```

must contain a runnable system.

No milestone may intentionally leave the system in a broken intermediate state.

---

## Rule 6 — Observability Is Mandatory

Every runtime operation must expose:

```text
run_id
trace_id
timestamps
status
errors
```

where applicable.

Features should not be considered complete if they cannot be debugged.

---

# 3. Target MVP

The MVP is considered complete when the following lifecycle works:

```text
Create Agent
    ↓
Configure Model
    ↓
Write Instructions
    ↓
Attach Tools
    ↓
Attach Knowledge
    ↓
Enable Memory
    ↓
Test Agent
    ↓
Inspect Trace
    ↓
Build Simple Workflow
    ↓
Use Child Agent
    ↓
Run Evaluation Dataset
    ↓
Publish New Version
    ↓
Compare Evaluation
    ↓
Deploy Agent
    ↓
Invoke Agent API
    ↓
Monitor Runs
```

---

# 4. Deferred Features

Do not implement these unless all MVP milestones are complete:

```text
Arbitrary code sandbox

Browser automation

Kubernetes

A2A

Advanced OAuth connector marketplace

Enterprise SSO

Multi-region runtime

Agent marketplace

Billing

Advanced organization RBAC

Full simulation engine

Hosted user-provided containers

Advanced hybrid search

Distributed vector database
```

---

# 5. Fixed Technical Decisions

Unless a blocking issue is discovered, Codex should treat these decisions as fixed.

## Backend

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
PostgreSQL
pgvector
```

Use async application patterns where useful.

---

## Frontend

```text
TypeScript
React
Next.js
```

Use server/client boundaries appropriately.

Do not put agent runtime logic in the frontend.

---

## Deployment

Primary deployment target:

```text
Google Cloud Run
```

Local development:

```text
Docker Compose
```

---

## Database

Primary:

```text
PostgreSQL
```

Initial managed environment:

```text
Supabase PostgreSQL
```

Vector search:

```text
pgvector
```

---

## Authentication

Initial:

```text
Supabase Auth
```

Backend must independently validate identity.

Frontend authorization is never sufficient.

---

## Files

Use a storage abstraction.

Production implementation:

```text
Google Cloud Storage
```

Local implementation:

```text
local filesystem or MinIO
```

Application code must not depend directly on GCS APIs outside the adapter.

---

## Model Providers

Implement initial providers:

```text
Google Gemini
OpenAI
```

Design provider abstraction for future:

```text
Anthropic
Amazon Bedrock
OpenRouter
Ollama
```

---

## Streaming

Use:

```text
Server-Sent Events
```

Do not introduce WebSockets unless required later.

---

## Observability

Use:

```text
structured JSON logs

internal execution spans

OpenTelemetry-compatible instrumentation
```

---

## MCP

Use the official/current Python MCP implementation available at development time.

MCP integrations must be normalized into the platform Tool abstraction.

---

# 6. Repository Structure

Create a monorepo:

```text
vibesfactory/
│
├── apps/
│   │
│   ├── api/
│   │   ├── app/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── worker/
│   │   ├── app/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   └── web/
│       ├── src/
│       ├── package.json
│       └── Dockerfile
│
├── packages/
│   │
│   ├── agents/
│   ├── models/
│   ├── runtime/
│   ├── sessions/
│   ├── tools/
│   ├── knowledge/
│   ├── memory/
│   ├── workflows/
│   ├── guardrails/
│   ├── evaluation/
│   ├── observability/
│   ├── deployments/
│   └── shared/
│
├── migrations/
│
├── infra/
│   ├── docker/
│   ├── gcp/
│   └── scripts/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/
│   ├── BRD.md
│   ├── ARCHITECTURE.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── API.md
│   └── ADR/
│
├── docker-compose.yml
├── .env.example
└── README.md
```

A single Python workspace/monorepo configuration may be used instead of separately published packages.

---

# 7. Backend Layer Pattern

Each bounded domain should generally use:

```text
domain/
application/
infrastructure/
api/
```

Example:

```text
agents/
│
├── domain/
│   ├── entities.py
│   ├── enums.py
│   └── exceptions.py
│
├── application/
│   ├── services.py
│   └── commands.py
│
├── infrastructure/
│   ├── models.py
│   └── repository.py
│
└── api/
    └── routes.py
```

Do not over-apply clean architecture abstractions where they add no value.

The goal is explicit domain boundaries, not maximum file count.

---

# 8. Core Domain Entities

The initial model must support the following entities.

```text
User

Workspace
WorkspaceMember

Agent
AgentVersion

ModelConfiguration

Session
Message

Run
RunStep
Trace
Span

Tool
ToolVersion
AgentTool

Credential

KnowledgeBase
Document
DocumentChunk
AgentKnowledgeBase

MemoryStore
MemoryItem

GuardrailPolicy

Workflow
WorkflowVersion
WorkflowNode
WorkflowEdge
WorkflowRun
WorkflowNodeRun

EvaluationDataset
EvaluationCase
EvaluationRun
EvaluationResult

Deployment

AuditLog
```

Not every entity needs its own service.

---

# 9. Required Global Identifiers

Use stable UUID identifiers.

Important resources:

```text
workspace_id

agent_id
agent_version_id

session_id

run_id

trace_id
span_id

tool_id
tool_version_id

knowledge_base_id
document_id

memory_store_id
memory_item_id

workflow_id
workflow_version_id
workflow_run_id

evaluation_dataset_id
evaluation_run_id

deployment_id
```

Do not use sequential IDs as public identifiers.

---

# 10. Global Database Conventions

Every major table should use where appropriate:

```text
id UUID

workspace_id UUID

created_at timestamptz

updated_at timestamptz
```

Soft deletion should be used only where product behavior requires it.

Do not automatically soft-delete everything.

JSONB may be used for:

```text
provider-specific metadata
tool configuration
trace attributes
runtime metadata
```

but core relational concepts should remain relational.

---

# 11. Phase 0 — Project Bootstrap

## Goal

Create the engineering foundation before implementing product features.

## Backend Tasks

Create:

```text
FastAPI application

health endpoint

configuration system

database session management

SQLAlchemy setup

Alembic setup

structured logging

global exception handling

request ID middleware

basic OpenTelemetry initialization
```

Health endpoints:

```text
GET /health
GET /ready
```

---

## Frontend Tasks

Create Next.js application with:

```text
root layout
navigation shell
login placeholder
dashboard placeholder
API client
environment configuration
```

---

## Infrastructure Tasks

Create:

```text
Dockerfile for API

Dockerfile for Web

docker-compose.yml

PostgreSQL container

optional Redis container

.env.example
```

---

## Development Tooling

Configure:

```text
ruff

mypy or pyright

pytest

pre-commit

ESLint

TypeScript strict mode

formatting
```

---

## CI

Initial GitHub Actions:

```text
backend lint

backend type check

backend tests

frontend lint

frontend type check

frontend build
```

---

## Required ADRs

Create:

```text
ADR-001 Modular Monolith

ADR-002 PostgreSQL System of Record

ADR-003 pgvector for MVP

ADR-004 Framework-Agnostic Agent Domain

ADR-005 SSE Streaming

ADR-006 Immutable Agent Versions

ADR-007 Session vs Memory vs Workflow State

ADR-008 OpenTelemetry-Compatible Tracing
```

---

## Acceptance Criteria

```text
docker compose up
```

starts a functional local environment.

The following work:

```text
GET /health

database migration

frontend application

CI pipeline
```

---

# 12. Phase 1 — Identity and Workspace Foundation

## Goal

Create secure tenant boundaries before storing platform resources.

## Database

Implement:

```text
users

workspaces

workspace_members
```

Workspace roles for MVP:

```text
OWNER
MEMBER
```

---

## Authentication

Integrate Supabase Auth.

Backend receives JWT and resolves:

```text
AuthenticatedPrincipal
```

containing:

```text
user_id
email
```

Do not trust workspace IDs supplied by frontend without authorization checks.

---

## Authorization

Create reusable authorization service:

```python
require_workspace_access(
    user_id,
    workspace_id,
)
```

Future RBAC should fit behind the same interface.

---

## API

Implement:

```text
GET  /v1/me

POST /v1/workspaces

GET  /v1/workspaces

GET  /v1/workspaces/{workspace_id}
```

---

## Frontend

Implement:

```text
Login

Workspace selection

Workspace shell

Basic settings page
```

---

## Tests

Must test:

```text
invalid JWT

expired JWT

workspace isolation

member can access workspace

non-member cannot access workspace
```

---

## Acceptance Criteria

Two different users cannot access each other's resources by modifying IDs in requests.

---

# 13. Phase 2 — Agent Control Plane

## Goal

Allow agents to be created and configured without yet implementing advanced runtime capabilities.

## Agent Entity

Agent represents mutable product identity:

```text
id

workspace_id

name

slug

description

status

current_draft_revision
```

Agent itself is not the deployment unit.

---

## Agent Draft

Use mutable configuration for editing.

Draft should support:

```text
model

instructions

runtime settings

tool references

knowledge references

memory configuration

guardrail references
```

---

## AgentVersion

Published snapshot must be immutable.

Suggested fields:

```text
id

agent_id

version_number

configuration JSONB

created_by

created_at
```

Configuration must contain everything necessary to reconstruct runtime behavior.

Do not resolve runtime behavior from mutable Agent state.

---

## ModelConfiguration

Normalized configuration:

```text
provider

model

temperature

max_output_tokens

reasoning_options

provider_options
```

---

## API

Implement:

```text
POST   /v1/agents

GET    /v1/agents

GET    /v1/agents/{agent_id}

PATCH  /v1/agents/{agent_id}

DELETE /v1/agents/{agent_id}

POST   /v1/agents/{agent_id}/versions

GET    /v1/agents/{agent_id}/versions

GET    /v1/agents/{agent_id}/versions/{version_id}
```

---

## Frontend

Create:

```text
Agents List

Create Agent

Agent Overview

Instructions Editor

Model Configuration

Versions Page
```

---

## Tests

Verify:

```text
draft changes do not mutate existing versions

published versions are immutable

version numbers increment correctly

agent names are workspace scoped

unauthorized users cannot edit agents
```

---

## Acceptance Criteria

A user can:

```text
Create Agent

Edit Instructions

Choose Model

Publish v1

Change Instructions

Publish v2

Inspect v1 and v2 independently
```

### Phase 2 delivery detail

Phase 2 is a control-plane-only vertical slice. It does not call model
providers or execute runtime, tools, knowledge, memory, guardrails, or
workflows. The implementation adds `agents`, `agent_drafts`, and immutable
`agent_versions` tables through migration `0003_agent_control_plane`.

Agent creation is workspace-scoped and transactionally creates the Agent
identity plus its single current AgentDraft. Draft edits use last-write-wins
with `updated_at` and `updated_by`; slug is create-only. Agent deletion means
archive, not hard deletion. `OWNER` and `MEMBER` retain the MVP permissions to
read, create, update, and publish agents.

Publishing locks the Agent row, validates the draft against a platform-owned
static model catalog, copies instructions/model/runtime/memory configuration
into a new AgentVersion, stores a complete snapshot with empty future binding
arrays, increments the version number, and commits atomically. Published
versions have no update or delete API.

The Phase 2 API includes Agent CRUD, draft read/update/validation, version
publish/list/detail, and `GET /v1/models`. The model catalog contains no
vendor SDK imports; Gemini/OpenAI adapters belong to Phase 3. Frontend work
includes the Agents list, creation form, detail editor, model configuration,
runtime/memory configuration placeholders, publish flow, and read-only
version inspection in both approved themes.

The database schema records `agent_versions.change_note` to keep the publish
API contract and persistence model aligned.

---

# 14. Phase 3 — Model Provider Layer

## Goal

Prevent provider APIs from leaking into runtime business logic.

## Core Interface

Implement conceptually:

```python
class ModelProvider(Protocol):

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        ...
```

---

## ModelRequest

Normalize:

```text
messages

system_instruction

tools

temperature

max_output_tokens

response_schema

stream

metadata
```

---

## ModelResponse

Normalize:

```text
content

tool_calls

usage

finish_reason

provider_metadata
```

---

## ToolCall

Normalized shape:

```text
id

name

arguments
```

---

## Usage

Normalized:

```text
input_tokens

output_tokens

cached_tokens
```

---

## Initial Adapters

Implement:

```text
GeminiProvider

OpenAIProvider
```

---

## Provider Registry

Create:

```text
ModelProviderRegistry
```

Responsibilities:

```text
resolve provider

return provider capabilities

validate configuration
```

---

## Model Capabilities

Track:

```text
tool_calling

streaming

structured_output

vision

reasoning

context_window
```

---

## Testing

Provider tests must primarily use fake/mock HTTP responses.

CI should not call paid external models.

Create:

```text
FakeModelProvider
```

for deterministic runtime testing.

---

# 15. Phase 4 — Runtime Vertical Slice v1

## Goal

This is the first critical milestone.

Create:

```text
Agent
→ Session
→ Runtime
→ LLM
→ Response
→ Run
→ Trace
```

without tools, RAG or memory.

---

# 16. Session Domain

Implement:

```text
sessions

messages
```

Session fields:

```text
id

workspace_id

agent_id

user_id

created_at

last_activity_at

metadata
```

Message:

```text
id

session_id

role

content

created_at

metadata
```

Roles:

```text
USER

ASSISTANT

TOOL

SYSTEM
```

---

# 17. Run Domain

Implement:

```text
runs
```

Fields:

```text
id

workspace_id

agent_id

agent_version_id

session_id

trace_id

status

input

output

error_code

error_message

started_at

completed_at

token_usage

estimated_cost

metadata
```

Statuses:

```text
QUEUED

RUNNING

WAITING_TOOL

WAITING_APPROVAL

COMPLETED

FAILED

CANCELLED
```

---

# 18. Runtime Contract

Implement:

```python
class AgentRuntime:

    async def run(
        self,
        request: AgentRunRequest,
    ) -> AgentRunResult:
        ...
```

Request:

```text
workspace_id

agent_version

session

input

execution_budget
```

---

# 19. Execution Budget

Implement from day one:

```text
max_steps

max_model_calls

max_tool_calls

max_child_runs

max_agent_depth

max_total_tokens

timeout_seconds
```

Initial default values should be conservative.

---

# 20. Context Builder v1

Input:

```text
Agent Instructions

Session Messages

User Input
```

Output:

```text
ModelRequest
```

Implement token accounting interface even if first version uses approximate token counting.

---

# 21. Runtime State

Execution:

```text
Create Run

Set RUNNING

Load AgentVersion

Load Session

Build Context

Call Model

Persist Assistant Message

Persist Usage

Set COMPLETED
```

On error:

```text
Set FAILED

Persist normalized error

Close trace
```

---

# 22. Trace Foundation

Create:

```text
traces

spans
```

Span fields:

```text
id

trace_id

parent_span_id

run_id

type

name

status

start_time

end_time

input

output

error

attributes
```

Initial span types:

```text
RUN

MODEL
```

---

# 23. Runtime API

Implement:

```text
POST /v1/agents/{agent_id}/runs

GET  /v1/runs/{run_id}

GET  /v1/runs/{run_id}/trace

GET  /v1/sessions/{session_id}

GET  /v1/sessions/{session_id}/messages
```

---

# 24. Playground

Build working agent playground.

UI:

```text
Chat panel

New Session

Agent Version selector

Run status

Basic token usage

Trace button
```

---

## Acceptance Criteria

User can:

```text
Create agent

Publish version

Open playground

Send message

Receive LLM response

Continue conversation

Reload page

See previous messages

Open run

Inspect model trace
```

This phase must be considered a major project checkpoint.

---

# 25. Phase 5 — Streaming

## Goal

Improve runtime UX without changing domain logic.

Implement SSE endpoint:

```text
POST /v1/agents/{agent_id}/runs:stream
```

or equivalent streaming contract.

Events:

```text
run.started

message.delta

message.completed

run.completed

run.failed
```

Later phases add:

```text
tool.started

tool.completed

knowledge.retrieved

memory.retrieved

agent.started

agent.completed
```

---

## Requirements

Streaming must not bypass persistence.

Final assistant message and Run record must be consistent with non-stream execution.

---

# 26. Phase 6 — Tool Platform

## Goal

Support model-controlled actions.

---

# 27. Tool Domain

Implement:

```text
tools

tool_versions

agent_tools
```

Tool:

```text
id

workspace_id

name

description

type

status
```

ToolVersion:

```text
input_schema

output_schema

executor_type

executor_config

timeout_seconds

retry_policy

risk_level

side_effect

idempotent
```

---

# 28. Initial Tool Types

Implement:

```text
FUNCTION

HTTP
```

Later:

```text
MCP

AGENT

WORKFLOW
```

---

# 29. Tool Executor Interface

```python
class ToolExecutor:

    async def execute(
        self,
        tool: ResolvedTool,
        arguments: dict,
        context: ToolExecutionContext,
    ) -> ToolResult:
        ...
```

---

# 30. Tool Invocation Pipeline

Required order:

```text
Model Tool Request
    ↓
Resolve Tool
    ↓
Validate Arguments
    ↓
Authorization
    ↓
Guardrail Hook
    ↓
Resolve Credential
    ↓
Execute
    ↓
Validate Output
    ↓
Redact Sensitive Data
    ↓
Trace
    ↓
Return to Model
```

---

# 31. Function Tools

Initial function tools should be registered by platform code.

Create at least:

```text
calculator

current_datetime or simple utility

echo/debug tool
```

Do not allow arbitrary Python upload.

---

# 32. HTTP Tools

Configuration:

```text
method

base_url

path

headers template

query mapping

body mapping

timeout

credential_ref
```

Security requirements:

```text
block private IP destinations

block localhost

block cloud metadata endpoints

limit redirects

limit response size

limit timeout

validate URL scheme
```

---

# 33. Runtime Tool Loop

Upgrade Runtime:

```text
Model
 ↓
tool_calls?
 ↓ yes
Execute Tools
 ↓
Append Tool Results
 ↓
Model
 ↓
repeat
```

Stop using ExecutionBudget.

---

# 34. Tool Tracing

Add span:

```text
TOOL
```

Attributes:

```text
tool_id

tool_version_id

tool_name

duration

status
```

---

## Acceptance Criteria

Agent can:

```text
choose a tool

call tool

receive result

use result in final answer
```

Trace displays:

```text
Model
Tool
Model
```

---

# 35. Phase 7 — Credential Vault

## Goal

Separate secrets from tools and agent configuration.

Implement:

```text
credentials
```

Fields:

```text
id

workspace_id

name

provider

credential_type

encrypted_value

metadata

created_by
```

---

# 36. Encryption

Do not invent custom cryptography.

Use a proper encryption library and a platform master key from environment/secret manager.

Production target later:

```text
Google Secret Manager
```

Database should never contain plaintext secrets.

---

# 37. Secret Resolution

Only Tool Executor or Model Provider should receive decrypted values.

Never put credentials into:

```text
LLM messages

traces

logs

frontend responses
```

---

# 38. Trace Redaction

Create centralized:

```text
SecretRedactor
```

Apply before persistence/logging.

---

# 39. Phase 8 — MCP Integration

## Goal

Make VibesFactory MCP-native.

---

# 40. MCP Server Resource

Add concept:

```text
MCPServer
```

Fields:

```text
id

workspace_id

name

transport

endpoint

credential_ref

status
```

---

# 41. MCP Manager

Responsibilities:

```text
connect

list tools

normalize schemas

execute tools

handle authentication

handle timeout

record traces
```

---

# 42. Tool Normalization

An MCP tool must become a standard:

```text
ResolvedTool
```

Runtime must not contain:

```text
if MCP ...
```

for normal execution behavior.

---

# 43. API/UI

Create:

```text
MCP Servers page

Add MCP Server

Test Connection

Discover Tools

Attach MCP Tool to Agent
```

---

## Acceptance Criteria

A test MCP server can expose tools which an agent discovers and executes.

Trace output is identical in shape to regular tools.

---

# 44. Phase 9 — Knowledge Base and RAG

## Goal

Add reusable private knowledge.

---

# 45. Knowledge Domain

Implement:

```text
knowledge_bases

documents

document_chunks

agent_knowledge_bases
```

---

# 46. KnowledgeBase

Fields:

```text
id

workspace_id

name

description

embedding_provider

embedding_model

status
```

---

# 47. Document

Fields:

```text
id

knowledge_base_id

name

mime_type

storage_uri

status

error

metadata

created_at
```

Statuses:

```text
UPLOADED

PROCESSING

READY

FAILED
```

---

# 48. DocumentChunk

Fields:

```text
id

document_id

knowledge_base_id

content

embedding

chunk_index

token_count

page_number

section

metadata
```

Create pgvector index.

---

# 49. Storage Abstraction

Implement:

```python
class BlobStore:
    async def put(...)
    async def get(...)
    async def delete(...)
```

Adapters:

```text
LocalBlobStore

GCSBlobStore
```

---

# 50. Ingestion Interface

Implement:

```python
class DocumentParser

class Chunker

class EmbeddingProvider
```

Initial supported formats:

```text
TXT

Markdown

PDF
```

DOCX can follow once core ingestion is stable.

---

# 51. Background Processing

API:

```text
Upload Document
    ↓
Persist UPLOADED
    ↓
enqueue ingestion
    ↓
return immediately
```

Worker:

```text
parse

normalize

chunk

embed

insert chunks

mark READY
```

---

# 52. Local Job Adapter

For local development, allow:

```text
inline/background dev execution
```

through a JobDispatcher abstraction.

Do not couple domain code directly to Google Cloud Tasks.

---

# 53. Production Job Adapter

Deployment milestone should implement:

```text
Google Cloud Tasks
        ↓
Authenticated Cloud Run worker endpoint
```

for asynchronous work.

Large batch-style operations may later use Cloud Run Jobs.

---

# 54. Retrieval Service

MVP:

```text
query

embed query

vector similarity search

workspace filter

knowledge base filter

top-k

return chunks
```

---

# 55. Retrieval Result

Normalize:

```text
chunk_id

document_id

content

score

source_name

page_number

metadata
```

---

# 56. Runtime Integration

Context Builder adds:

```text
Knowledge Context
```

before calling model.

Create trace span:

```text
RETRIEVAL
```

---

# 57. Citations

Runtime must retain retrieved chunk IDs.

Response metadata should support:

```text
citations[]
```

Do not rely solely on model-generated citations.

---

## Acceptance Criteria

User can:

```text
Create knowledge base

Upload PDF

Wait until READY

Attach KB to agent

Ask document question

Receive grounded answer

See retrieved chunks

See source/page metadata
```

---

# 58. Phase 10 — Memory

## Goal

Implement memory separately from sessions.

---

# 59. Memory Domain

Implement:

```text
memory_stores

memory_items
```

Memory types:

```text
PROFILE

SEMANTIC

SUMMARY

PROCEDURAL
```

---

# 60. MemoryItem

Fields:

```text
id

memory_store_id

workspace_id

user_id

agent_id nullable

type

content

embedding

importance

confidence

source_session_id

created_at

expires_at nullable

metadata
```

---

# 61. Memory Read Path

```text
User Request
    ↓
Memory Query
    ↓
Embedding
    ↓
Scoped Search
    ↓
Top Memories
    ↓
Context Builder
```

Trace:

```text
MEMORY_RETRIEVAL
```

---

# 62. Memory Write Path

After successful interactions:

```text
Conversation
    ↓
Candidate Extraction
    ↓
Filter
    ↓
Deduplicate
    ↓
Persist
```

Initially run asynchronously.

---

# 63. Memory Extraction

Use model with structured output.

Candidate:

```json
{
  "type": "PROFILE",
  "content": "User prefers Python.",
  "importance": 0.8
}
```

---

# 64. Memory Deduplication

Before insert:

```text
search similar memories

compare semantic similarity

skip or update duplicate
```

Do not blindly store every conversation.

---

# 65. Memory UI

Create:

```text
Agent Memory Settings

Memory Browser

Delete Memory

Edit/Correct Memory
```

---

## Acceptance Criteria

User provides preference in Session A.

Session B can retrieve it without receiving Session A history.

---

# 66. Phase 11 — Guardrails

## Goal

Implement execution boundaries.

---

# 67. Guardrail Interface

```python
class Guardrail:

    async def evaluate(
        self,
        context: GuardrailContext,
    ) -> GuardrailDecision:
        ...
```

Decision:

```text
ALLOW

BLOCK

REDACT

REQUIRE_APPROVAL
```

---

# 68. Guardrail Hooks

Implement hooks:

```text
INPUT

MODEL_OUTPUT

TOOL_INPUT

TOOL_OUTPUT
```

---

# 69. Initial Guardrails

Implement deterministic versions first:

```text
regex block

secret detection

PII-like redaction

tool allow/deny

tool risk level

maximum payload size
```

Optional model-based safety classifier can follow.

---

# 70. Trace

Create:

```text
GUARDRAIL
```

spans/events.

Never expose sensitive matched values unnecessarily.

---

# 71. Phase 12 — Workflow Engine v1

## Goal

Implement deterministic orchestration separately from agent runtime.

---

# 72. Workflow Domain

Implement:

```text
workflows

workflow_versions

workflow_nodes

workflow_edges

workflow_runs

workflow_node_runs
```

---

# 73. Node Types for MVP

Implement:

```text
START

END

AGENT

TOOL

CONDITION

TRANSFORM
```

Defer:

```text
PARALLEL

APPROVAL
```

until sequential engine is stable.

---

# 74. Workflow Version

Workflow draft is mutable.

Published workflow version is immutable.

Same pattern as AgentVersion.

---

# 75. Workflow Run State

Persist:

```text
status

current_node

variables

node_outputs

error
```

Do not keep workflow state only in process memory.

---

# 76. Node Executor Interface

```python
class WorkflowNodeExecutor:

    async def execute(
        self,
        node,
        context,
    ) -> NodeExecutionResult:
        ...
```

---

# 77. Agent Node

Agent node calls:

```text
AgentRuntime
```

Do not duplicate agent invocation logic.

---

# 78. Tool Node

Tool node calls:

```text
ToolExecutor
```

Do not duplicate tool logic.

---

# 79. Condition Node

Use explicit deterministic expression rules.

Do not use arbitrary Python `eval()`.

---

## Acceptance Criteria

Workflow:

```text
START

↓

Research Agent

↓

Condition

├── sufficient → Writer Agent
└── insufficient → Search Tool

↓

END
```

can execute with persisted state and traceable node runs.

---

# 80. Phase 13 — Multi-Agent

## Goal

Make agent composition a first-class capability.

---

# 81. Agent-as-Tool

Implement new Tool executor:

```text
AGENT
```

Configuration:

```text
target_agent_id

target_agent_version or deployment strategy
```

---

# 82. Child Runs

On invocation:

```text
Parent Run

↓

Child Run
```

Store:

```text
parent_run_id

root_run_id

agent_depth
```

---

# 83. Runtime Safety

Enforce:

```text
max_agent_depth

max_child_runs

max_total_steps

max_total_tokens
```

---

# 84. Supervisor Pattern

UI allows attaching child agents to a supervisor.

Runtime exposes child agents as tools.

Example:

```text
research

analyze

write
```

---

# 85. Trace Tree

Trace Viewer must render nested runs.

Example:

```text
Supervisor

├── Research Agent
│   ├── Model
│   └── Search Tool
│
├── Analyst Agent
│
└── Writer Agent
```

---

## Acceptance Criteria

Supervisor dynamically delegates work to at least two child agents.

Nested traces remain correlated.

---

# 86. Phase 14 — Human-in-the-Loop

## Goal

Support approval-sensitive actions.

---

# 87. Approval Domain

Implement:

```text
approval_requests
```

Fields:

```text
id

workspace_id

run_id

tool_call_id

status

requested_action

arguments

risk_reason

requested_at

resolved_at

resolved_by
```

Statuses:

```text
PENDING

APPROVED

REJECTED

EXPIRED
```

---

# 88. Runtime Behavior

```text
Tool Guardrail

↓

REQUIRE_APPROVAL

↓

Persist Approval

↓

Run = WAITING_APPROVAL
```

Approval:

```text
Approve

↓

Resume exact pending action

↓

Execute Tool
```

Do not call the model again to regenerate the tool arguments.

---

# 89. Phase 15 — Evaluation Platform

## Goal

Make agent quality measurable.

---

# 90. Evaluation Domain

Implement:

```text
evaluation_datasets

evaluation_cases

evaluation_runs

evaluation_results
```

---

# 91. EvaluationCase

Fields:

```text
input

expected_output nullable

expected_tool nullable

expected_schema nullable

rubric nullable

metadata
```

---

# 92. Evaluator Interface

```python
class Evaluator:

    async def evaluate(
        self,
        case,
        run,
    ) -> EvaluationResult:
        ...
```

---

# 93. MVP Evaluators

Implement:

```text
ContainsEvaluator

ExactMatchEvaluator

JSONSchemaEvaluator

ToolCallEvaluator

LatencyEvaluator
```

Then:

```text
LLMJudgeEvaluator

GroundednessEvaluator
```

---

# 94. Evaluation Execution

Always invoke:

```text
AgentRuntime
```

Do not implement special agent logic for evaluations.

---

# 95. Batch Execution

Evaluation should be asynchronous.

```text
Create EvaluationRun

↓

enqueue cases

↓

run agents

↓

run evaluators

↓

aggregate score
```

---

# 96. Evaluation Comparison

UI must compare:

```text
Agent v1

vs

Agent v2
```

Metrics:

```text
success

quality

latency

tokens

estimated cost

tool correctness
```

---

## Acceptance Criteria

Same dataset can be run against two versions and produce a comparison report.

---

# 97. Phase 16 — Deployment Domain

## Goal

Separate internal testing from stable production invocation.

---

# 98. Deployment Entity

Implement:

```text
deployments
```

Fields:

```text
id

workspace_id

agent_id

agent_version_id

name

environment

status

created_at
```

Environments:

```text
DEVELOPMENT

STAGING

PRODUCTION
```

---

# 99. Deployment Rules

Deployment always references:

```text
AgentVersion
```

never Agent draft.

---

# 100. Public Invocation

Implement:

```text
POST /v1/deployments/{deployment_id}/runs
```

External authentication:

```text
API key
```

---

# 101. API Key Domain

Implement hashed API keys.

Store:

```text
key_prefix

key_hash

workspace_id

deployment_id nullable

created_at

revoked_at
```

Never store raw key after creation.

---

# 102. Deployment Rollback

Support:

```text
deployment v3

↓

change pointer

↓

v2
```

No agent configuration mutation required.

---

# 103. Phase 17 — Monitoring and Cost

## Goal

Turn raw execution traces into operational understanding.

---

# 104. Monitoring Metrics

Dashboard:

```text
Runs

Success Rate

Failure Rate

Average Latency

P95 Latency

Input Tokens

Output Tokens

Tool Failures

Estimated Cost
```

Filters:

```text
time range

agent

version

model

status
```

---

# 105. Pricing Registry

Implement:

```text
provider

model

effective_from

input_price

output_price

cached_input_price nullable
```

Cost should be marked:

```text
estimated
```

not authoritative billing.

---

# 106. Usage Aggregation

Initially query operational DB.

Later introduce aggregate tables only if necessary.

Do not prematurely build separate analytics infrastructure.

---

# 107. Phase 18 — Trace Viewer

## Goal

Make observability a standout portfolio feature.

---

# 108. Trace Tree

Render:

```text
Run

├── Memory
├── Retrieval
├── Model
├── Tool
├── Child Agent
│   └── Model
└── Model
```

---

# 109. Span Inspector

Show:

```text
duration

status

input

output

attributes

tokens

cost

error
```

Sensitive values must be redacted.

---

# 110. Timeline View

Optional after tree view works.

Do not prioritize timeline visualization over functional trace tree.

---

# 111. Phase 19 — Product UI Consolidation

At this point the major backend capabilities exist.

Refine navigation:

```text
Dashboard

Build
├── Agents
├── Workflows
├── Tools
├── Knowledge
└── Memory

Operate
├── Deployments
├── Runs
├── Traces
└── Monitoring

Evaluate
├── Datasets
├── Evaluation Runs
└── Comparisons

Platform
├── Models
├── MCP
├── Credentials
├── Guardrails
└── Settings
```

---

# 112. Agent Detail UI

Tabs:

```text
Overview

Instructions

Model

Tools

Knowledge

Memory

Guardrails

Agents

Playground

Versions

Deployments
```

---

# 113. UI Philosophy

Do not initially build a complex drag-and-drop agent builder.

Configuration forms are enough.

Workflow visual editor may be added after workflow API is stable.

---

# 114. Phase 20 — Cloud Run Deployment

## Goal

Create reproducible portfolio deployment.

---

# 115. Services

Deploy:

```text
vibesfactory-api

vibesfactory-worker

vibesfactory-web
```

Frontend may remain on Vercel if preferred.

---

# 116. Recommended Cloud Run API Configuration

Initial:

```text
1 vCPU

512 MiB or 1 GiB RAM

min instances = 0

max instances = 2

concurrency = 10

request timeout = conservative interactive limit
```

---

# 117. Worker Architecture

Production async flow:

```text
API

↓

Cloud Tasks

↓

Authenticated worker endpoint

↓

Cloud Run Worker
```

Worker scales to zero.

Use idempotency keys.

---

# 118. GCP Resources

Create:

```text
Cloud Run

Artifact Registry

Cloud Build or GitHub Actions

Cloud Tasks

Google Cloud Storage

Secret Manager

Service Accounts
```

PostgreSQL initially remains:

```text
Supabase
```

---

# 119. Service Accounts

Separate identities:

```text
api-service-account

worker-service-account
```

Use least privilege.

---

# 120. Secret Manager

Production secrets:

```text
DATABASE_URL

SUPABASE secrets

MODEL provider keys if system-managed

ENCRYPTION_MASTER_KEY

worker authentication secrets
```

Do not bake secrets into Docker images.

---

# 121. CI/CD

On pull request:

```text
lint

type check

unit tests

integration tests

frontend build
```

On merge to main:

```text
build container

push Artifact Registry

deploy Cloud Run

run smoke tests
```

Database migration should be a deliberate deployment step.

Do not have every API container independently run migrations on startup.

---

# 122. Phase 21 — Security Hardening

Perform structured review.

---

# 123. Required Security Checks

Review:

```text
workspace isolation

JWT verification

API key hashing

credential encryption

secret redaction

HTTP tool SSRF

tool argument validation

upload validation

file size limits

document parsing safety

SQL injection

prompt injection boundaries

rate limiting

CORS

error disclosure

audit logging
```

---

# 124. Rate Limits

Add limits for:

```text
public deployments

model calls

tool calls

file uploads
```

---

# 125. File Security

Validate:

```text
allowed MIME types

maximum file size

filename sanitization

storage object paths
```

Never execute uploaded files.

---

# 126. Phase 22 — Reliability Hardening

Implement normalized retry rules.

Retry:

```text
429

transient 5xx

temporary network failures
```

Do not blindly retry:

```text
401

403

validation failure

guardrail rejection

non-idempotent side-effect tools
```

---

# 127. Idempotency

Required for:

```text
document ingestion

evaluation jobs

deployment creation where appropriate

async task processing
```

Store or derive idempotency keys.

---

# 128. Timeouts

Configure separately:

```text
model timeout

tool timeout

child agent timeout

workflow node timeout

overall run timeout
```

---

# 129. Error Taxonomy

Create normalized errors:

```text
ProviderError

ToolError

RetrievalError

MemoryError

GuardrailViolation

ValidationError

RateLimitError

TimeoutError

AuthorizationError

WorkflowError

PlatformError
```

---

# 130. Phase 23 — Test Suite Completion

The system must have four test layers.

---

## Unit Tests

Prioritize deterministic logic:

```text
context builder

execution budgets

tool schema validation

guardrails

workflow routing

memory deduplication

cost calculation

version publishing

permission checks
```

---

## Integration Tests

Test:

```text
PostgreSQL repositories

pgvector retrieval

fake model runtime

tool executor

MCP test server

document ingestion

workflow persistence
```

---

## E2E Tests

Required scenarios:

### E2E 1

```text
Create Agent

Publish Version

Invoke

Receive Response
```

### E2E 2

```text
Agent

→ Tool

→ Final Response
```

### E2E 3

```text
Upload Document

→ Ingest

→ RAG Answer
```

### E2E 4

```text
Session A

→ Memory

→ Session B
```

### E2E 5

```text
Supervisor

→ Child Agent

→ Result
```

### E2E 6

```text
Evaluation v1

→ Evaluation v2

→ Compare
```

### E2E 7

```text
Deploy Agent

→ API Key

→ Public Invocation
```

---

# 131. Fake Model Provider

This is mandatory.

Implement deterministic test model able to simulate:

```text
plain response

tool call

multiple tool calls

invalid tool arguments

provider failure

timeout

streaming response
```

This allows runtime testing without spending model tokens.

---

# 132. Fake Tool Executor

Test tools should support:

```text
success

failure

timeout

non-idempotent behavior

guardrail rejection
```

---

# 133. Phase 24 — Documentation

Required repository documentation:

```text
README.md

BRD.md

ARCHITECTURE.md

IMPLEMENTATION_PLAN.md

API.md

LOCAL_DEVELOPMENT.md

DEPLOYMENT.md

SECURITY.md
```

---

# 134. README Structure

README should show:

```text
What is VibesFactory?

Architecture Diagram

Core Features

Quick Start

Screenshots

Example Agent

Example Trace

Example Multi-Agent Flow

Tech Stack

Development

Deployment

Roadmap
```

---

# 135. Portfolio Demo Scenario

Create one polished demonstration scenario.

Recommended:

> Technical Research Team

Agents:

```text
Research Agent

Analyst Agent

Writer Agent
```

Knowledge:

```text
uploaded technical documentation
```

Tools:

```text
HTTP search-like tool

MCP tool
```

Memory:

```text
user output preferences
```

Workflow:

```text
Research

↓

Analysis

↓

Report
```

Evaluation:

```text
10–20 curated test cases
```

---

# 136. Demo Lifecycle

Demo should show:

```text
Create Agent

↓

Attach Tool

↓

Attach Knowledge

↓

Run

↓

Inspect Trace

↓

Create Multi-Agent Flow

↓

Evaluate v1

↓

Modify Prompt

↓

Publish v2

↓

Evaluation Improves

↓

Deploy v2

↓

Invoke through API
```

This is the primary portfolio narrative.

---

# 137. Suggested Milestone Order

Codex should implement in this exact order unless a discovered dependency requires adjustment:

```text
M0  Project Bootstrap

M1  Authentication + Workspace

M2  Agent Control Plane

M3  Model Provider Layer

M4  Runtime v1 + Sessions + Runs + Tracing

M5  Streaming

M6  Tools

M7  Credentials

M8  MCP

M9  Knowledge + RAG

M10 Memory

M11 Guardrails

M12 Workflow

M13 Multi-Agent

M14 Human Approval

M15 Evaluation

M16 Deployments + Public API

M17 Monitoring + Cost

M18 Trace Viewer Polish

M19 Product UI Consolidation

M20 Cloud Run Infrastructure

M21 Security Hardening

M22 Reliability Hardening

M23 Full Test Suite

M24 Documentation + Portfolio Demo
```

Do not implement later milestones merely because they appear easy.

---

# 138. Critical Dependency Graph

```text
Foundation
    │
    ▼
Auth / Workspace
    │
    ▼
Agent Control Plane
    │
    ▼
Model Provider
    │
    ▼
Runtime
    │
    ├───────────────┬────────────────┐
    ▼               ▼                ▼
  Tools            RAG             Memory
    │               │                │
    └───────────────┴────────────────┘
                    │
                    ▼
               Guardrails
                    │
             ┌──────┴──────┐
             ▼             ▼
          Workflow      Multi-Agent
             │             │
             └──────┬──────┘
                    ▼
                Evaluation
                    │
                    ▼
                Deployment
                    │
                    ▼
          Monitoring / Operations
```

---

# 139. Feature Flags

Incomplete capabilities should remain behind feature flags.

Examples:

```text
ENABLE_MCP

ENABLE_MEMORY

ENABLE_WORKFLOWS

ENABLE_MULTI_AGENT

ENABLE_EVALUATION
```

Do not expose half-functional modules in production UI.

---

# 140. Database Migration Rules

Every schema modification must:

```text
include Alembic migration

support upgrade

avoid destructive changes unless documented

be tested on populated development DB
```

Do not manually modify production tables.

---

# 141. API Rules

All public APIs:

```text
/v1/...
```

Use consistent error shape:

```json
{
  "error": {
    "code": "TOOL_EXECUTION_FAILED",
    "message": "Tool execution failed.",
    "request_id": "..."
  }
}
```

Do not expose Python stack traces.

---

# 142. Pagination

List endpoints should support pagination from the beginning.

Use either:

```text
limit / cursor
```

or consistent offset strategy.

Cursor pagination is preferred for high-volume operational resources such as Runs.

---

# 143. API Idempotency

Public run creation may support:

```text
Idempotency-Key
```

later.

Async administrative operations should use stable job identifiers.

---

# 144. Runtime Invariants

Codex must preserve these invariants.

## Invariant 1

A Run always references an immutable:

```text
AgentVersion
```

---

## Invariant 2

A Deployment always references an immutable:

```text
AgentVersion
```

---

## Invariant 3

Historical traces do not change when the Agent draft changes.

---

## Invariant 4

Session messages and long-term memories are separate resources.

---

## Invariant 5

Workflow execution state is not stored inside conversational memory.

---

## Invariant 6

Raw credentials never enter model context.

---

## Invariant 7

External tool arguments are validated before execution.

---

## Invariant 8

Evaluation runs use the same AgentRuntime as normal runs.

---

## Invariant 9

Child agents create separate Runs.

---

## Invariant 10

Every external side effect must be traceable.

---

# 145. Performance Guidelines

Do not optimize prematurely.

However prevent obvious issues:

```text
N+1 database queries

loading entire conversation histories

unbounded trace payloads

unbounded tool responses

unbounded agent loops

large DB connection pools

embedding one chunk per HTTP request sequentially
```

---

# 146. Context Management

Create explicit:

```text
ContextBuilder
```

rather than constructing prompts throughout runtime code.

Inputs:

```text
system policy

instructions

session

memory

knowledge

tools

workflow context
```

---

# 147. Token Budgeting

ContextBuilder should enforce:

```text
model context window

reserved output budget
```

Priority example:

```text
System policy

Instructions

Current request

Relevant tools

Recent session

Memory

Knowledge

Older history
```

Never blindly include all stored information.

---

# 148. Model Failure Handling

Providers may return:

```text
rate limit

timeout

invalid response

tool schema mismatch

content restriction
```

Normalize these into platform error types.

Do not leak provider exception classes throughout runtime.

---

# 149. Tool Safety Metadata

Each ToolVersion should include:

```text
risk_level

side_effect

idempotent
```

Suggested risk:

```text
LOW

MEDIUM

HIGH
```

Example:

```text
search issues
LOW

create issue
MEDIUM

delete repository
HIGH
```

---

# 150. Audit Events

Implement audit events for:

```text
agent.created

agent.version.published

deployment.created

deployment.updated

credential.created

tool.created

approval.approved

approval.rejected
```

Do not use execution traces as a replacement for audit logs.

---

# 151. Observability Event Names

Prefer stable event names:

```text
run.started

run.completed

run.failed

model.started

model.completed

tool.started

tool.completed

tool.failed

retrieval.completed

memory.retrieved

memory.created

guardrail.blocked

approval.requested

agent.child_started

agent.child_completed

evaluation.completed
```

---

# 152. Telemetry Storage Policy

Internal database traces power the VibesFactory Trace Viewer.

OpenTelemetry is used as an export/integration path.

Do not require an external OTel backend for local development.

---

# 153. Local Development Experience

Target developer workflow:

```bash
git clone ...

cp .env.example .env

docker compose up -d

make migrate

make seed

make dev
```

Equivalent task runner commands may be used.

---

# 154. Seed Data

Provide development seed:

```text
Demo Workspace

Demo Agent

Fake Model

Calculator Tool

Small Knowledge Base

Evaluation Dataset
```

This greatly improves local testing.

---

# 155. Environment Separation

Support:

```text
local

development

production
```

Configuration must come from environment variables or secret management.

Never branch application logic heavily based on environment.

---

# 156. Cloud Portability

Application code should remain deployable to:

```text
Cloud Run

Docker

ECS

Kubernetes
```

without changing core domain logic.

Cloud-specific logic belongs under:

```text
infrastructure/
```

---

# 157. Definition of Done — Feature

A feature is not complete unless:

```text
domain implemented

database migration added

authorization applied

API implemented

validation implemented

errors normalized

tracing added

unit tests added

integration tests added where applicable

frontend implemented if user-facing

documentation updated
```

---

# 158. Definition of Done — Milestone

A milestone is complete only when:

```text
CI passes

Docker environment works

database migrations work

existing E2E tests pass

new acceptance criteria pass

no known critical security issue exists

documentation reflects changes
```

---

# 159. Coding Agent Rules

Codex should follow these rules.

### Do not invent new architecture silently.

If implementation requires changing an architectural decision:

```text
create or update ADR
```

and document the reason.

### Do not introduce major dependencies without reason.

Prefer standard Python capabilities and narrowly scoped libraries.

### Do not replace platform abstractions with framework-specific objects.

Bad:

```python
Agent = LangGraphGraph
```

Good:

```python
AgentVersion
    ↓
Runtime Adapter
    ↓
LangGraph optional
```

### Do not commit secrets.

### Do not disable tests to make CI pass.

### Do not swallow runtime exceptions.

### Do not expose raw provider errors to clients.

### Do not combine multiple milestones in one uncontrolled change.

---

# 160. Recommended Pull Request Strategy

Each PR should ideally represent one cohesive capability.

Examples:

```text
feat(workspaces): add workspace isolation

feat(agents): add immutable agent versions

feat(runtime): implement model-only runtime

feat(tools): add function tool execution

feat(rag): add pgvector retrieval

feat(memory): add semantic memory retrieval
```

Avoid:

```text
feat: implement entire platform
```

---

# 161. Commit Convention

Recommended:

```text
feat:

fix:

refactor:

test:

docs:

chore:

perf:

security:
```

---

# 162. Branching

Simple strategy:

```text
main

feature/*
```

Main should always be deployable.

No complex GitFlow required.

---

# 163. First Implementation Slice for Codex

The coding agent should start only with:

```text
Phase 0

Phase 1

Phase 2

Phase 3

Phase 4
```

Target outcome:

```text
Authenticated User

↓

Workspace

↓

Create Agent

↓

Publish Agent Version

↓

Invoke Agent

↓

Model Provider

↓

Persist Session

↓

Persist Run

↓

Persist Trace

↓

Display Result
```

Do not begin RAG until this works.

---

# 164. First Major Quality Gate

Before Tool implementation begins, verify:

```text
Agent versions are immutable.

Runtime uses AgentVersion.

Sessions persist.

Runs persist.

Model abstraction works with FakeModelProvider.

At least one real model provider works.

Failures create failed Runs.

Traces contain model spans.

Workspace isolation is tested.

Playground works end-to-end.
```

If any item fails, fix it before Phase 6.

---

# 165. Second Major Quality Gate

Before Workflow/Multi-Agent:

```text
Tool execution stable.

Credentials isolated.

MCP normalized as tools.

RAG stable.

Memory separated from sessions.

Guardrails intercept tool execution.

Trace viewer can debug all these operations.
```

---

# 166. Third Major Quality Gate

Before public deployment:

```text
Workflow stable.

Multi-agent child runs bounded.

Evaluation works.

Version comparison works.

API keys secure.

Rate limits exist.

Credential redaction tested.

Security review completed.
```

---

# 167. Suggested Final MVP Feature Matrix

| Capability | MVP |
|---|---|
| Agent CRUD | Yes |
| Agent Versioning | Yes |
| Multi-model | Yes |
| Playground | Yes |
| Sessions | Yes |
| Streaming | Yes |
| Tools | Yes |
| HTTP Tools | Yes |
| MCP | Yes |
| RAG | Yes |
| Knowledge | Yes |
| Citations | Yes |
| Memory | Yes |
| Guardrails | Yes |
| Workflow | Yes |
| Multi-Agent | Yes |
| Human Approval | Yes |
| Traces | Yes |
| Monitoring | Yes |
| Cost Tracking | Yes |
| Evaluation | Yes |
| Version Comparison | Yes |
| Deployment | Yes |
| Public API | Yes |
| Cloud Run | Yes |
| A2A | No |
| Code Sandbox | No |
| Browser | No |
| Kubernetes | No |
| Hosted custom agents | No |
| Connector marketplace | No |

---

# 168. MVP Completion Criteria

VibesFactory MVP is complete only when this scenario succeeds reliably:

```text
1. User logs in.

2. User creates workspace.

3. User creates Research Agent.

4. User chooses Gemini or OpenAI.

5. User writes instructions.

6. User publishes Agent v1.

7. User creates Knowledge Base.

8. User uploads documentation.

9. Document reaches READY.

10. User attaches Knowledge Base.

11. User adds HTTP or MCP tool.

12. User enables Memory.

13. User chats with Agent.

14. Agent retrieves knowledge.

15. Agent calls tool.

16. Agent returns answer with source metadata.

17. User opens Trace Viewer.

18. User sees:
    memory
    retrieval
    model
    tool
    model.

19. User creates Analyst Agent.

20. Research Agent invokes Analyst Agent.

21. User sees nested child run.

22. User creates evaluation dataset.

23. User evaluates v1.

24. User modifies instructions.

25. User publishes v2.

26. User evaluates v2.

27. User compares scores.

28. User deploys v2.

29. User creates API key.

30. User invokes deployed agent externally.

31. Monitoring dashboard reports:
    runs
    latency
    tokens
    errors
    estimated cost.
```

If this complete lifecycle works, the project is portfolio-ready.

---

# 169. Post-MVP Roadmap

Only after MVP completion:

```text
Advanced hybrid search

Reranking

Visual workflow editor

Parallel workflow branches

Advanced memory policies

Agent Registry

A2A

Connector SDK

OAuth connector framework

Browser runtime

Code Interpreter

Hosted custom agents

Simulation

Online evaluation

Prompt optimization

Enterprise RBAC

Organization management

Cloud SQL deployment

Dedicated Redis

Runtime service extraction

Tool Gateway service
```

---

# 170. Final Implementation Strategy

The core development sequence can be summarized as:

```text
FOUNDATION
    ↓
IDENTITY
    ↓
AGENT DEFINITION
    ↓
MODEL ABSTRACTION
    ↓
RUNTIME
    ↓
OBSERVABILITY
    ↓
TOOLS
    ↓
MCP
    ↓
RAG
    ↓
MEMORY
    ↓
GUARDRAILS
    ↓
WORKFLOW
    ↓
MULTI-AGENT
    ↓
HUMAN APPROVAL
    ↓
EVALUATION
    ↓
DEPLOYMENT
    ↓
MONITORING
    ↓
CLOUD RUN
    ↓
HARDENING
```

The most important architectural principle throughout implementation remains:

> VibesFactory is not an application containing a few AI agents.  
> VibesFactory is infrastructure that allows other AI agents to be created, executed, connected, observed, evaluated and deployed.

Therefore every implementation decision should prioritize reusable platform primitives over one-off agent behavior.

---

# Appendix A — Codex Kickoff Instructions

The following instructions can be supplied to the coding agent together with the BRD, System Architecture and this Implementation Plan.

```text
You are implementing VibesFactory, a production-inspired Agentic AI Platform.

Read these documents before modifying code:

1. BRD.md
2. ARCHITECTURE.md
3. IMPLEMENTATION_PLAN.md

Treat them as the project source of truth.

Implementation rules:

- Follow milestone order from IMPLEMENTATION_PLAN.md.
- Do not implement future milestones unless required by an explicit dependency.
- Preserve framework-agnostic domain boundaries.
- Do not couple Agent entities directly to LangChain, LangGraph, or a model vendor.
- Published AgentVersion objects must be immutable.
- Runtime executions must always reference AgentVersion.
- Separate Session, Memory and Workflow State.
- Never expose credentials to LLM context.
- Every runtime feature must emit trace information.
- Evaluation must invoke the same runtime used by normal requests.
- Use PostgreSQL as the system of record.
- Use pgvector for MVP semantic search.
- Use FastAPI for backend services.
- Use Next.js for frontend.
- Target Docker locally and Cloud Run for deployment.
- Write migrations for all schema changes.
- Add tests with every feature.
- Keep CI green.
- Never commit secrets.
- Document architectural deviations using ADRs.

For each milestone:

1. Inspect existing code.
2. State the implementation scope.
3. Implement backend domain and persistence.
4. Add migration.
5. Implement API.
6. Add tests.
7. Implement required frontend.
8. Run lint/type checks/tests.
9. Update documentation.
10. Stop after milestone acceptance criteria are satisfied.

Do not optimize for maximum feature count.
Optimize for correctness, maintainability, observability and a working end-to-end lifecycle.
```

---

# Appendix B — Recommended First Codex Task

```text
Implement Milestone M0 — Project Bootstrap only.

Deliver:

- Python FastAPI backend skeleton.
- Next.js frontend skeleton.
- PostgreSQL Docker service.
- SQLAlchemy database configuration.
- Alembic migrations.
- Pydantic configuration system.
- Structured JSON logging.
- request_id middleware.
- GET /health.
- GET /ready.
- pytest setup.
- backend lint/type-check configuration.
- frontend lint/type-check configuration.
- Dockerfiles.
- docker-compose.yml.
- .env.example.
- GitHub Actions CI.
- docs/ADR containing ADR-001 through ADR-008 placeholders with accepted decisions.

Do not implement Agents, authentication, RAG, tools, workflows or model providers yet.

Acceptance criteria:

- docker compose up starts the local stack.
- backend /health returns HTTP 200.
- backend can connect to PostgreSQL.
- Alembic upgrade head succeeds.
- frontend starts successfully.
- backend tests pass.
- frontend build succeeds.
- CI configuration is present.
```
