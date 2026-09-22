# ADR-012: Durable workflow execution and replayable observation

## Status

Accepted for the expanded Phase 12 milestone.

## Decision

VibesFactory owns the v1 workflow graph contract, persistence, expression
evaluation, queue execution, budget accounting, and observability semantics.
Workflows are published as immutable normalized versions and run asynchronously
from PostgreSQL leased jobs. Each node is represented by a `WorkflowNodeRun`;
the cursor, variables, outputs, error, and usage are committed before the next
node is selected. Model, HTTP, and MCP calls happen outside the transaction.

`WorkflowRunEvent` is an append-only sequence. The API exposes it through an
authenticated fetch-based SSE stream with `Last-Event-ID` replay. Event data is
safe metadata; authenticated run/node/span endpoints are used for payload
details. This makes a browser reload or worker reconnect observable without
reconstructing state from process memory.

Agent nodes reuse `AgentRuntime`. Supervisor child agents are published as
immutable, pinned bindings and are exposed as normalized model tools. A shared
execution budget enforces depth, child runs, steps, model/tool calls, tokens,
and absolute deadline. Child failures are normalized tool failures; budget,
timeout, and cancellation failures fail the root execution. Phase 12 does not
invent approval/resume or parallel scheduling.

## Consequences

- Completed nodes are not replayed after queue redelivery.
- A worker restart during an active agent or side-effect operation fails closed
  with `WORKFLOW_RESUME_UNSAFE`; the system never guesses whether an external
  action happened.
- PostgreSQL is both the durable control plane and event replay source. Event
  retention/compaction is intentionally deferred to the reliability phase.
- React Flow is a presentation/editor layer only. The backend validator and
  published normalized graph remain the source of truth.

## Implementation record (2026-09-22)

The runtime carries one mutable `ExecutionContext` through the workflow,
agent-node, and supervisor child-run tree. It owns the absolute deadline,
lineage IDs, and cumulative node, step, model, tool, child, agent, and token
counters. Limits are checked before external calls and a limit, deadline,
cancellation, or child failure fails the root execution with a normalized
error. Child `Run` and `Span` rows are created with parent/root/trace/workflow
and parent-span relationships before runtime execution; no post-hoc
re-parenting is used.

Workflow-only traces remain visible in the trace collection even when no root
agent run exists. Child-agent lifecycle events contain only safe lineage,
version, status, duration, error-code, and usage metadata. Direct children are
available through the workspace-scoped `GET /v1/runs/{run_id}/children`
collection endpoint.
