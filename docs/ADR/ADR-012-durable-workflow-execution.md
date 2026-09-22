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
