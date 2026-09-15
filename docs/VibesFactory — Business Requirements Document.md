# VibesFactory — Business Requirements Document

**Document Version:** 0.2  
**Document Status:** Approved Baseline  
**Project:** VibesFactory  
**Project Type:** Learning / Portfolio Project with Future Productization Potential  
**Primary Audience:** Product Owner, AI Engineer, Backend Engineer, Software Architect, Coding Agents

---

# 1. Executive Summary

VibesFactory is a self-hostable platform for creating, configuring, running, orchestrating, observing, evaluating, versioning, and deploying AI agents.

The platform is inspired by the capabilities and architectural patterns of leading agent platforms including:

- Amazon Bedrock AgentCore
- Microsoft Foundry Agent Service
- Microsoft Copilot Studio
- Google Gemini Enterprise Agent Platform
- MCP-compatible agent/tool ecosystems
- Emerging agent interoperability standards such as A2A

VibesFactory does not attempt to reproduce hyperscale cloud infrastructure.

Instead, it implements a focused subset of production-style Agent Platform capabilities in a:

- Model-agnostic
- Framework-agnostic
- Extensible
- Self-hostable
- Cloud-portable

architecture.

The initial purpose of VibesFactory is educational and portfolio-oriented.

The platform should demonstrate practical understanding of:

- Agent architecture
- Agent runtime design
- LLM orchestration
- Prompt and context engineering
- Retrieval-Augmented Generation
- Knowledge management
- Memory
- Tool calling
- MCP
- Workflow orchestration
- Multi-agent systems
- Guardrails
- Human-in-the-loop execution
- Observability
- Evaluation
- Versioning
- Deployment
- Cloud-native software engineering

The target user lifecycle is:

```text
Create Agent
    ↓
Configure Model
    ↓
Write Instructions
    ↓
Attach Knowledge
    ↓
Attach Memory
    ↓
Attach Tools / MCP
    ↓
Configure Guardrails
    ↓
Compose Workflow / Agents
    ↓
Test in Playground
    ↓
Inspect Trace
    ↓
Evaluate
    ↓
Publish Version
    ↓
Deploy
    ↓
Invoke through API
    ↓
Monitor
    ↓
Improve
```

The long-term vision is for VibesFactory to become:

> An extensible platform for building, running, connecting, observing, evaluating, and deploying production-style AI agents.

---

# 2. Product Name

Official product name:

> **VibesFactory**

The name represents the idea of a factory in which developers assemble:

```text
Models
+
Instructions
+
Knowledge
+
Memory
+
Tools
+
Agents
+
Workflows
+
Runtime
```

into deployable AI systems.

The product name should be written as:

```text
VibesFactory
```

rather than:

```text
Vibes Factory
vibesfactory
Vibesfactory
```

except where lowercase naming is technically required, such as:

```text
vibesfactory-api
vibesfactory-worker
vibesfactory-web
```

---

# 3. Business Context

Generative AI applications are evolving from simple conversational interfaces into systems capable of:

- Reasoning over complex tasks
- Selecting external tools
- Retrieving private knowledge
- Maintaining conversation state
- Remembering users across sessions
- Delegating tasks
- Executing workflows
- Coordinating specialized agents
- Operating external applications
- Running asynchronously
- Recovering from failures
- Being monitored and evaluated

Cloud providers are increasingly packaging these capabilities into managed Agent Platforms.

Common platform capabilities include:

```text
Agent Builder
Agent Runtime
Knowledge
RAG
Memory
Tools
Connectors
Tool Gateway
Identity
Guardrails
Workflow
Multi-Agent
Tracing
Monitoring
Evaluation
Versioning
Deployment
Governance
```

Managed platforms are useful but hide much of the underlying engineering.

VibesFactory is intended to expose and implement these concepts explicitly.

The primary educational question behind the project is:

> What does the infrastructure behind a modern production AI agent platform actually look like?

---

# 4. Problem Statement

Developers building AI agents commonly create applications where many infrastructure concerns are tightly coupled.

Typical application:

```text
Frontend
   ↓
Agent Framework
   ↓
LLM Provider
   ↓
Vector Database
   ↓
Custom Tool Code
```

This approach may work for one agent but becomes difficult to manage as the system grows.

Common problems include:

- Model-provider lock-in
- Framework lock-in
- Duplicated tool integrations
- Repeated credential management
- Missing execution history
- Poor observability
- No agent version lifecycle
- No evaluation system
- Weak memory management
- No workflow persistence
- No reusable knowledge abstraction
- No multi-agent governance
- Difficult deployment
- Inconsistent runtime behavior

VibesFactory addresses these problems by providing reusable platform primitives shared across agents.

---

# 5. Product Vision

VibesFactory shall provide one unified environment to:

> **Build, connect, run, orchestrate, observe, evaluate, version, and deploy AI agents.**

VibesFactory should progressively support three development modes.

---

## 5.1 Configuration-Based Agent

A user configures:

```text
Model
Instructions
Tools
Knowledge
Memory
Guardrails
```

without writing orchestration code.

VibesFactory owns the runtime loop.

---

## 5.2 Workflow-Based System

Users combine deterministic workflows and AI agents.

Example:

```text
START
 ↓
Retrieve Customer
 ↓
Support Agent
 ↓
Condition
 ↓
Human Approval
 ↓
Refund Tool
 ↓
END
```

---

## 5.3 Code-Based Agent

Future versions may support developer-provided agents based on:

- Custom Python
- LangGraph
- OpenAI Agents SDK
- Google ADK
- Other frameworks

These agents should still be exposed through the same VibesFactory runtime/deployment interface.

---

# 6. Product Positioning

VibesFactory should be positioned as:

> A lightweight, production-inspired Agent Platform for developers.

It should not claim to replace:

- Amazon Bedrock AgentCore
- Microsoft Foundry
- Google Gemini Enterprise Agent Platform
- Microsoft Copilot Studio

Instead:

> VibesFactory implements the core architectural patterns behind modern Agent-as-a-Service platforms in an open and understandable form.

---

# 7. Business Objectives

## BO-01 — Learn Production Agent Architecture

VibesFactory shall provide hands-on experience implementing:

- LLM abstractions
- Context management
- Agent execution loops
- Tool execution
- RAG
- Memory
- Workflows
- Multi-agent orchestration
- Async execution
- Observability
- Evaluations
- Security boundaries
- Cloud infrastructure

---

## BO-02 — Produce a Strong Technical Portfolio

The project shall demonstrate significantly more engineering depth than a conventional chatbot.

The portfolio should demonstrate:

```text
Python
FastAPI
API design
PostgreSQL
Vector databases
Async programming
LLM engineering
Agentic AI
Distributed systems
Observability
Security
Cloud deployment
Frontend/backend integration
System design
```

---

## BO-03 — Support Multiple Agent Use Cases

The platform shall not be designed around one agent.

Example applications:

- Research agent
- Coding agent
- Support agent
- Document assistant
- Data agent
- Knowledge assistant
- Automation agent
- Technical research team
- Multi-agent analysis system

---

## BO-04 — Extensibility

Major capabilities should be represented by abstractions.

Examples:

```text
ModelProvider
ToolExecutor
EmbeddingProvider
VectorStore
BlobStore
MemoryStrategy
Evaluator
AgentRuntime
JobDispatcher
```

---

## BO-05 — Low Operating Cost

The initial deployment should prefer free or inexpensive services.

Priorities:

- Scale-to-zero compute
- Low idle cost
- BYOK model credentials
- Free database tier where possible
- Cloud-portable containers

---

## BO-06 — Future Product Potential

VibesFactory architecture should not prevent future evolution into:

- Open-source agent platform
- Developer SaaS
- Enterprise agent platform
- Agent observability platform
- Evaluation platform
- MCP gateway
- Agent runtime infrastructure

---

# 8. Non-Goals

The initial VibesFactory project shall not attempt to provide:

- Global hyperscale infrastructure
- Multi-region active-active
- Enterprise SLAs
- SOC 2 certification
- HIPAA certification
- Complex enterprise IAM
- Hundreds of connectors
- Full marketplace
- Kubernetes-first infrastructure
- Arbitrary untrusted code execution
- Full browser automation infrastructure
- SaaS billing
- GPU model hosting
- Large-scale model serving

These capabilities may be considered after the core platform is complete.

---

# 9. Target Users

## Persona 1 — AI Developer

Needs:

- Create agent
- Configure LLM
- Write instructions
- Attach tools
- Add RAG
- Add memory
- Test agent
- Deploy agent
- Debug runs

---

## Persona 2 — Python / Backend Developer

Needs:

- Extend providers
- Add tools
- Add connectors
- Build evaluators
- Implement new runtime capabilities
- Integrate infrastructure

---

## Persona 3 — AI Engineer

Needs:

- Analyze traces
- Evaluate agent quality
- Compare versions
- Detect failures
- Inspect retrieval
- Inspect token usage
- Diagnose tool behavior

---

## Persona 4 — Platform Administrator

Future needs:

- Manage shared resources
- Manage credentials
- Audit changes
- Manage permissions
- Monitor infrastructure

---

# 10. Product Principles

## P-01 — Model Agnostic

VibesFactory shall support different model providers.

Potential providers:

```text
Google Gemini
OpenAI
Anthropic
Amazon Bedrock
OpenRouter
Ollama
OpenAI-compatible providers
```

---

## P-02 — Framework Agnostic

The VibesFactory domain model shall not depend on:

```text
LangChain
LangGraph
CrewAI
OpenAI Agents SDK
Google ADK
```

These may be optional adapters.

---

## P-03 — Protocol First

Prefer open protocols:

```text
HTTP
REST
OpenAPI
MCP
A2A
OpenTelemetry
```

where appropriate.

---

## P-04 — Observability First

Every important execution must be inspectable.

The platform should answer:

> What happened during this run?

---

## P-05 — Version Important Resources

Resources such as:

```text
Agent
Tool
Guardrail
Workflow
```

should support immutable published versions.

---

## P-06 — Separate Deterministic and Agentic Execution

VibesFactory shall model:

```text
Workflow Engine
```

and:

```text
Agent Runtime
```

as related but distinct systems.

---

## P-07 — Human Control for Sensitive Actions

High-risk operations should support:

```text
ALLOW
BLOCK
REQUIRE APPROVAL
```

policies.

---

# 11. Product Domains

VibesFactory consists of:

```text
Agent Management

Model Management

Prompt / Instructions

Playground

Sessions

Knowledge

RAG

Memory

Tools

MCP

Connectors

Credentials

Agent Runtime

Workflow

Multi-Agent

Guardrails

Human Approval

Tracing

Monitoring

Evaluation

Versioning

Deployment

Public API

Administration
```

---

# 12. Agent Management Requirements

## FR-AGT-001

Users shall be able to create agents.

Required initial fields:

```text
Name
Description
Model
Instructions
```

Priority: **Must Have**

---

## FR-AGT-002

Users shall be able to update agent drafts.

Priority: **Must Have**

---

## FR-AGT-003

Users should be able to clone agents.

Priority: **Should Have**

---

## FR-AGT-004

Users shall be able to archive agents.

Priority: **Must Have**

---

## FR-AGT-005

Agents should expose lifecycle states.

Example:

```text
ACTIVE
ARCHIVED
```

Priority: **Should Have**

---

# 13. Model Requirements

## FR-MDL-001

Support multiple providers through a common abstraction.

Priority: **Must Have**

---

## FR-MDL-002

Expose supported configuration such as:

```text
temperature
max tokens
reasoning options
structured output
```

Priority: **Must Have**

---

## FR-MDL-003

Support Bring Your Own Key.

Priority: **Must Have**

---

## FR-MDL-004

Switching compatible model providers should not require changing agent business logic.

Priority: **Must Have**

---

# 14. Prompt Requirements

## FR-PRM-001

Agents shall support configurable instructions.

Priority: **Must Have**

---

## FR-PRM-002

Reusable prompt variables/templates should eventually be supported.

Priority: **Should Have**

---

## FR-PRM-003

Published instructions shall be captured inside immutable AgentVersions.

Priority: **Must Have**

---

# 15. Playground

## FR-PLY-001

Users shall be able to interactively test agents.

Priority: **Must Have**

---

## FR-PLY-002

Responses should support streaming.

Priority: **Should Have**

---

## FR-PLY-003

Users should inspect:

```text
tool calls
retrieval
memory
tokens
latency
trace
```

Priority: **Must Have**

---

# 16. Sessions

## FR-SES-001

Each conversation shall belong to a Session.

Priority: **Must Have**

---

## FR-SES-002

Messages shall be persisted.

Priority: **Must Have**

---

## FR-SES-003

Sessions shall be isolated by user/workspace.

Priority: **Must Have**

---

## FR-SES-004

Retention/expiration policies may be added later.

Priority: **Could Have**

---

# 17. Knowledge Management

## FR-KNW-001

Users shall create reusable Knowledge Bases.

Priority: **Must Have**

---

## FR-KNW-002

Initial file support:

```text
PDF
TXT
Markdown
```

DOCX may follow.

Priority: **Must Have**

---

## FR-KNW-003

Users shall manage document lifecycle:

```text
upload
processing
ready
failed
delete
```

Priority: **Must Have**

---

## FR-KNW-004

One Knowledge Base may be shared by multiple Agents.

Priority: **Should Have**

---

# 18. RAG

## FR-RAG-001

VibesFactory shall implement:

```text
Document
 ↓
Parse
 ↓
Normalize
 ↓
Chunk
 ↓
Embed
 ↓
Index
```

Priority: **Must Have**

---

## FR-RAG-002

Semantic vector retrieval shall be supported.

Priority: **Must Have**

---

## FR-RAG-003

Metadata filters should be supported.

Priority: **Should Have**

---

## FR-RAG-004

Hybrid retrieval may be added later.

Priority: **Could Have**

---

## FR-RAG-005

Reranking may be added later.

Priority: **Could Have**

---

## FR-RAG-006

Retrieval provenance and citations should be exposed.

Priority: **Should Have**

---

# 19. Memory

VibesFactory shall distinguish:

```text
Session History
Memory
Workflow State
```

---

## FR-MEM-001

Short-term conversational context shall be supported.

Priority: **Must Have**

---

## FR-MEM-002

Long-term memory shall persist selected information across sessions.

Priority: **Must Have**

---

## FR-MEM-003

User profile memories should be supported.

Priority: **Should Have**

---

## FR-MEM-004

Conversation summary memory should be supported.

Priority: **Should Have**

---

## FR-MEM-005

Semantic retrieval of memories should be supported.

Priority: **Should Have**

---

## FR-MEM-006

Users should eventually be able to inspect, edit, or delete memories.

Priority: **Should Have**

---

# 20. Tools

## FR-TOL-001

Developers shall register platform-defined function tools.

Priority: **Must Have**

---

## FR-TOL-002

Tools shall expose:

```text
name
description
input schema
output schema
```

Priority: **Must Have**

---

## FR-TOL-003

HTTP APIs shall be usable as tools.

Priority: **Must Have**

---

## FR-TOL-004

OpenAPI import may be supported later.

Priority: **Should Have**

---

## FR-TOL-005

Tools shall be reusable across agents.

Priority: **Must Have**

---

## FR-TOL-006

Tool calls shall be traced.

Priority: **Must Have**

---

## FR-TOL-007

Tool execution shall support timeouts.

Priority: **Must Have**

---

## FR-TOL-008

Safe retry behavior should be supported.

Priority: **Should Have**

---

# 21. MCP

## FR-MCP-001

VibesFactory shall operate as an MCP client.

Priority: **Must Have**

---

## FR-MCP-002

MCP tool discovery shall be supported.

Priority: **Must Have**

---

## FR-MCP-003

MCP tools shall be normalized into the VibesFactory Tool abstraction.

Priority: **Must Have**

---

## FR-MCP-004

VibesFactory may later expose its own MCP server.

Priority: **Should Have**

---

# 22. Connectors

## FR-CON-001

The architecture shall support reusable Connector resources.

Potential integrations:

```text
GitHub
Slack
Jira
Google Drive
Notion
PostgreSQL
HTTP APIs
```

Priority: **Should Have**

---

## FR-CON-002

Connector credentials shall remain separate from agents.

Priority: **Must Have**

---

# 23. Credentials

## FR-SEC-001

Secrets shall be encrypted.

Priority: **Must Have**

---

## FR-SEC-002

Secrets must be redacted from:

```text
logs
traces
model context
errors
API responses
```

Priority: **Must Have**

---

## FR-SEC-003

Agents and tools shall reference Credential resources rather than embedding secrets.

Priority: **Must Have**

---

# 24. Agent Runtime

## FR-RUN-001

VibesFactory shall expose a consistent invocation abstraction.

Conceptually:

```text
POST /v1/agents/{agent_id}/runs
```

Priority: **Must Have**

---

## FR-RUN-002

Configuration-based agents shall support an execution loop.

```text
Request
 ↓
Build Context
 ↓
Model
 ↓
Decision
 ↓
Tool / Agent / Response
 ↓
Repeat
```

Priority: **Must Have**

---

## FR-RUN-003

Every invocation shall produce a Run.

Priority: **Must Have**

---

## FR-RUN-004

Run states shall include:

```text
QUEUED
RUNNING
WAITING_TOOL
WAITING_APPROVAL
COMPLETED
FAILED
CANCELLED
```

Priority: **Must Have**

---

## FR-RUN-005

Streaming should use SSE.

Priority: **Should Have**

---

## FR-RUN-006

Execution cancellation should eventually be supported.

Priority: **Should Have**

---

## FR-RUN-007

Long-running execution shall be architecturally supported through asynchronous jobs.

Priority: **Should Have**

---

# 25. Execution Budget

VibesFactory shall limit agent execution.

Example limits:

```text
max_steps
max_model_calls
max_tool_calls
max_child_runs
max_agent_depth
max_total_tokens
timeout_seconds
```

This prevents accidental infinite loops and runaway costs.

Priority: **Must Have**

---

# 26. Workflow

## FR-WKF-001

VibesFactory shall support deterministic workflows.

Priority: **Must Have**

---

## FR-WKF-002

MVP node types:

```text
START
END
AGENT
TOOL
CONDITION
TRANSFORM
```

Later:

```text
PARALLEL
APPROVAL
```

Priority: **Must Have**

---

## FR-WKF-003

Workflow state shall persist independently from Session and Memory.

Priority: **Must Have**

---

## FR-WKF-004

Conditional routing shall be supported.

Priority: **Must Have**

---

## FR-WKF-005

Failure and retry behavior should be configurable.

Priority: **Should Have**

---

# 27. Multi-Agent

## FR-MAG-001

Agents shall be able to invoke other agents.

Priority: **Must Have**

---

## FR-MAG-002

Supervisor orchestration shall be supported.

Priority: **Must Have**

---

## FR-MAG-003

Sequential execution shall be supported.

Priority: **Must Have**

---

## FR-MAG-004

Parallel orchestration may be added later.

Priority: **Should Have**

---

## FR-MAG-005

Agent handoff may be added later.

Priority: **Should Have**

---

## FR-MAG-006

A2A interoperability is post-MVP.

Priority: **Could Have**

---

# 28. Guardrails

## FR-GRD-001

Inputs shall support guardrail interception.

Priority: **Must Have**

---

## FR-GRD-002

Outputs shall support guardrail interception.

Priority: **Must Have**

---

## FR-GRD-003

Tool calls shall support guardrail interception.

Priority: **Must Have**

---

## FR-GRD-004

Decisions shall support:

```text
ALLOW
BLOCK
REDACT
REQUIRE_APPROVAL
```

Priority: **Must Have**

---

# 29. Human-in-the-Loop

## FR-HITL-001

Sensitive operations shall support approval.

Priority: **Should Have**

---

## FR-HITL-002

Execution shall resume from persisted state.

Priority: **Should Have**

---

## FR-HITL-003

Approval decisions shall be auditable.

Priority: **Should Have**

---

# 30. Tracing

## FR-TRC-001

Every Run shall produce a trace.

Priority: **Must Have**

---

## FR-TRC-002

Span types may include:

```text
RUN
MODEL
TOOL
RETRIEVAL
MEMORY_RETRIEVAL
GUARDRAIL
WORKFLOW_NODE
CHILD_AGENT
```

Priority: **Must Have**

---

## FR-TRC-003

Trace detail should expose:

```text
duration
input
output
error
model
tokens
tool arguments
retrieved chunks
```

after appropriate redaction.

Priority: **Must Have**

---

## FR-TRC-004

Tracing should be OpenTelemetry-compatible.

Priority: **Should Have**

---

# 31. Monitoring

## FR-MON-001

VibesFactory shall provide an operational dashboard.

Priority: **Must Have**

---

## FR-MON-002

Metrics should include:

```text
runs
success rate
failure rate
average latency
P95 latency
model latency
tool failures
token usage
```

Priority: **Must Have**

---

## FR-MON-003

Estimated cost should be tracked where model pricing is available.

Priority: **Should Have**

---

# 32. Evaluation

Evaluation remains distinct from monitoring.

Monitoring:

> What happened?

Evaluation:

> Was the behavior good?

---

## FR-EVL-001

Users shall create Evaluation Datasets.

Priority: **Must Have**

---

## FR-EVL-002

AgentVersions shall run against datasets.

Priority: **Must Have**

---

## FR-EVL-003

Deterministic evaluators shall support:

```text
exact match
contains
tool call
JSON schema
latency
```

Priority: **Must Have**

---

## FR-EVL-004

LLM-as-Judge should be supported.

Priority: **Should Have**

---

## FR-EVL-005

AgentVersion comparison should be supported.

Priority: **Should Have**

---

## FR-EVL-006

Regression detection may be implemented later.

Priority: **Could Have**

---

# 33. Versioning

## FR-VER-001

Published AgentVersions shall be immutable.

Priority: **Must Have**

---

## FR-VER-002

Historical versions shall remain inspectable.

Priority: **Must Have**

---

## FR-VER-003

Deployment rollback shall be supported by changing version references.

Priority: **Should Have**

---

# 34. Deployment

## FR-DEP-001

Users shall deploy an AgentVersion.

Priority: **Must Have**

---

## FR-DEP-002

Deployments shall expose stable invocation endpoints.

Priority: **Must Have**

---

## FR-DEP-003

External invocation shall require authentication.

Priority: **Must Have**

---

## FR-DEP-004

A Deployment shall always reference an immutable AgentVersion.

Priority: **Must Have**

---

# 35. Developer API

## FR-API-001

Core resources shall expose REST APIs.

Priority: **Must Have**

---

## FR-API-002

API documentation shall be available.

Priority: **Must Have**

---

## FR-API-003

A Python SDK may be implemented later.

Priority: **Should Have**

---

## FR-API-004

A CLI may be implemented later.

Priority: **Could Have**

---

# 36. Conceptual Domain Model

```text
Workspace
│
├── Agents
│   ├── Draft
│   ├── Versions
│   ├── Sessions
│   ├── Runs
│   └── Deployments
│
├── Tools
│   └── Versions
│
├── MCP Servers
│
├── Credentials
│
├── Knowledge Bases
│   └── Documents
│       └── Chunks
│
├── Memory Stores
│   └── Memories
│
├── Guardrails
│   └── Versions
│
├── Workflows
│   └── Versions
│       └── Runs
│
├── Evaluation Datasets
│   └── Evaluation Runs
│
├── Traces
└── Audit Logs
```

---

# 37. State Model

VibesFactory shall maintain strict separation between:

### Session State

Conversation state.

```text
messages
active conversation
```

### Memory

Information learned across interactions.

```text
preferences
facts
summaries
procedures
```

### Workflow State

Process execution progress.

```text
current node
variables
waiting approval
completed nodes
```

These concepts shall not be merged.

---

# 38. Core User Journey — Build Agent

```text
Login
 ↓
Workspace
 ↓
Create Agent
 ↓
Select Model
 ↓
Write Instructions
 ↓
Publish Version
 ↓
Open Playground
 ↓
Invoke
 ↓
Inspect Trace
```

---

# 39. Core User Journey — Knowledge

```text
Create Knowledge Base
 ↓
Upload Document
 ↓
Background Ingestion
 ↓
READY
 ↓
Attach to Agent
 ↓
Ask Question
 ↓
Retrieve Chunks
 ↓
Answer
 ↓
Inspect Sources
```

---

# 40. Core User Journey — Tool

```text
Create Tool
 ↓
Publish Tool Version
 ↓
Attach Tool to Agent
 ↓
Invoke Agent
 ↓
Model Selects Tool
 ↓
Guardrail
 ↓
Execute Tool
 ↓
Return Result
 ↓
Final Response
```

---

# 41. Core User Journey — Memory

```text
Session A
 ↓
User shares preference
 ↓
Memory Extraction
 ↓
Memory Store

New Session B
 ↓
Relevant Memory Retrieval
 ↓
Personalized Response
```

---

# 42. Core User Journey — Multi-Agent

```text
Supervisor
   │
   ├── Research Agent
   ├── Analyst Agent
   └── Writer Agent
```

Nested Runs and Traces must remain inspectable.

---

# 43. Core User Journey — Evaluation

```text
Agent v1
 ↓
Dataset
 ↓
Score A

Change Agent
 ↓
Publish v2
 ↓
Same Dataset
 ↓
Score B

Compare
 ↓
Deploy Better Version
```

---

# 44. Non-Functional Requirements

## NFR-01 — Security

VibesFactory shall:

- Protect credentials
- Validate external inputs
- Redact secrets
- Isolate workspaces
- Restrict dangerous tools
- Avoid arbitrary untrusted code execution in MVP

---

## NFR-02 — Extensibility

New providers or implementations shall fit behind defined interfaces.

---

## NFR-03 — Portability

Core application logic should not depend on Cloud Run-specific APIs.

---

## NFR-04 — Cost Efficiency

Idle infrastructure should consume minimal compute.

---

## NFR-05 — Observability

Execution failures must be debuggable from platform telemetry.

---

## NFR-06 — Reliability

Failures in tools or model providers should not corrupt durable state.

---

## NFR-07 — Maintainability

Boundaries must remain clear between:

```text
Agents
Runtime
Tools
Knowledge
Memory
Workflow
Evaluation
Observability
```

---

## NFR-08 — Developer Experience

Local development should work without requiring production cloud infrastructure.

---

## NFR-09 — Auditability

Important administrative actions shall eventually produce audit logs.

---

# 45. Business Rules

## BR-01

Agents must not contain provider-specific runtime business logic.

## BR-02

Credentials shall not be embedded inside Agent configuration.

## BR-03

Runs shall reference immutable AgentVersions.

## BR-04

Deployments shall reference immutable AgentVersions.

## BR-05

Session, Memory, and Workflow State remain separate.

## BR-06

Memory shall have explicit ownership/scope.

## BR-07

Evaluation results shall identify the AgentVersion evaluated.

## BR-08

Guardrails may block or suspend tool execution.

## BR-09

Approval requests shall preserve the exact pending action.

## BR-10

Historical traces shall remain understandable after configuration changes.

---

# 46. MVP Scope

MVP includes:

```text
Authentication
Workspace Isolation

Agent CRUD
Agent Draft
Agent Versioning

Gemini Provider
OpenAI Provider

Playground
Sessions
Streaming

Runtime
Execution Budgets

Function Tools
HTTP Tools
Credential Vault
MCP Client

Knowledge Bases
PDF/TXT/Markdown
RAG
pgvector
Citations

Short-Term Context
Long-Term Memory

Guardrails
Human Approval

Workflow

Supervisor Multi-Agent

Tracing
Trace Viewer

Monitoring
Cost Estimation

Evaluation Datasets
Deterministic Evaluators
LLM Judge
Version Comparison

Deployment
API Keys
Public Invocation

Cloud Run Deployment
```

---

# 47. Post-MVP Scope

Potential later features:

```text
Hybrid Search

Reranking

Visual Workflow Builder

Parallel Workflows

Parallel Agents

Agent Handoff

A2A

Agent Registry

Connector SDK

OAuth Connectors

Browser Runtime

Code Interpreter

Hosted Custom Agent Containers

Simulation

Online Evaluation

Prompt Optimization

Advanced RBAC

Enterprise SSO

Cloud SQL

Dedicated Tool Gateway
```

---

# 48. Explicitly Deferred

Do not block MVP on:

```text
Kubernetes
multi-region
enterprise billing
marketplace
browser automation
arbitrary Python sandbox
custom model serving
GPU hosting
hundreds of connectors
```

---

# 49. Success Criteria

A portfolio-ready VibesFactory release must demonstrate:

1. User authentication.
2. Workspace isolation.
3. Agent creation.
4. Agent version publication.
5. Multiple LLM providers.
6. Sessions.
7. Tool calling.
8. MCP.
9. RAG.
10. Long-term memory.
11. Guardrails.
12. Workflow.
13. Multi-agent delegation.
14. Tracing.
15. Evaluation.
16. Version comparison.
17. Deployment.
18. Public API invocation.
19. Monitoring.
20. Cost estimation.

---

# 50. Portfolio Demo Scenario

Recommended showcase:

> **VibesFactory Technical Research Team**

Agents:

```text
Research Agent
Analyst Agent
Writer Agent
```

Resources:

```text
Knowledge Base
HTTP Tool
MCP Tool
Memory
Guardrails
```

Execution:

```text
Research
 ↓
Analysis
 ↓
Writing
```

Then:

```text
Evaluate v1
 ↓
Modify Agent
 ↓
Publish v2
 ↓
Evaluate v2
 ↓
Compare
 ↓
Deploy
```

---

# 51. Key Risks

## Scope Explosion

Mitigation:

```text
strict milestones
vertical slices
deferred feature list
```

## Framework Lock-In

Mitigation:

```text
VibesFactory-owned abstractions
```

## Model Lock-In

Mitigation:

```text
ModelProvider adapters
```

## Runtime Complexity

Mitigation:

```text
simple synchronous runtime first
async later
```

## Tool Security

Mitigation:

```text
schema validation
risk metadata
guardrails
approval
audit
```

## Memory Quality

Mitigation:

```text
candidate extraction
deduplication
relevance
explicit scope
```

## RAG Quality

Mitigation:

```text
trace retrieval
evaluate
add hybrid/reranking later
```

## Evaluation Ambiguity

Mitigation:

```text
deterministic tests
LLM judge
tool assertions
human review
```

---

# 52. Product Maturity Model

## Level 1 — Agent Builder

```text
Prompt
Model
Tools
RAG
Playground
```

## Level 2 — Agent Platform

```text
Memory
Runtime
Workflow
Multi-Agent
Versions
Deployments
```

## Level 3 — Production Agent Platform

```text
Tracing
Monitoring
Evaluation
Guardrails
Approval
Identity
```

## Level 4 — Agent Infrastructure

```text
Agent Registry
MCP Gateway
A2A
Hosted Code
Advanced Governance
Simulation
Enterprise Integration
```

The initial portfolio release should achieve:

> Strong Level 2 + selected high-value Level 3 capabilities.

---

# 53. Definition of Portfolio-Ready

VibesFactory is portfolio-ready when a developer can:

```text
Create Agent
 ↓
Select Gemini/OpenAI
 ↓
Configure Instructions
 ↓
Attach Tool
 ↓
Attach MCP
 ↓
Attach Knowledge
 ↓
Enable Memory
 ↓
Run
 ↓
Inspect Trace
 ↓
Create Multi-Agent System
 ↓
Evaluate
 ↓
Publish Improved Version
 ↓
Deploy
 ↓
Invoke with API Key
 ↓
Inspect Monitoring
```

without modifying application code for the individual agent.

---

# 54. Final Requirement Statement

VibesFactory shall provide reusable infrastructure enabling developers to:

> **Build, connect, run, orchestrate, observe, evaluate, version, and deploy AI agents.**

The initial project prioritizes:

```text
Architectural clarity
Extensibility
Observability
Developer learning
Production-style engineering
Low operational cost
```

over hyperscale infrastructure.

VibesFactory is based on the principle that a modern AI agent is not merely:

```text
LLM + Prompt
```

but a system composed of:

```text
Model
+
Instructions
+
Context
+
Knowledge
+
Memory
+
Tools
+
Workflow
+
Agents
+
Runtime
+
Security
+
Observability
+
Evaluation
```

VibesFactory exists to provide that surrounding system.

---

# 55. Document Approval Criteria

This BRD is considered the baseline when the following remain accepted:

- VibesFactory is model agnostic.
- VibesFactory is framework agnostic.
- Agent versions are immutable.
- Workflow and Agent Runtime remain separate.
- Session, Memory, and Workflow State remain separate.
- Tracing is a first-class feature.
- Evaluation is a first-class feature.
- MCP is part of MVP.
- Multi-agent is part of MVP.
- Cloud Run is the primary deployment target.
- PostgreSQL is the primary system of record.
- pgvector is the initial vector solution.
- Low-cost self-hosting remains an initial constraint.