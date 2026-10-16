# Agent runtime execution

`AgentRuntime` in `apps/api/app/runtime/service.py` is the stable facade for
the synchronous `run()` and `stream()` entrypoints. It composes invocation
execution loops with collaborators that own model access, accounting,
retrieval, persistence lifecycle, and tool batches.

## Dependency map

- `RunExecution` and `StreamExecution` own their transport-specific loop and
  use `AgentRuntime` for shared guardrail, provider, context, and tool behavior.
- `RunLifecycle` owns trace/run/message persistence, completion, failure, and
  cancellation. It shares `RuntimeAccounting` for cost aggregation.
- `ModelAccessResolver` resolves published model connections and credentials.
- `RuntimeRetrieval` owns memory and knowledge retrieval and citation updates.
- `ToolBatchExecutor` evaluates and executes calls sequentially, persists tool
  records, and handles child-agent calls and approval pauses.
- Each loop creates a `RunState`; its guardrail events and tracker are scoped
  to that invocation. The shared runtime instance does not hold invocation
  state.
- `runs/request_builder.py` builds runtime requests independently of HTTP
  routes. Routes retain compatibility imports for existing callers.

## Persistence and ordering checkpoints

The lifecycle starts a trace, run, root span, and user message before committing
the running state. Guardrail evaluation persists its span before the evaluated
input can enter runtime history. Context and model spans are committed at their
existing checkpoints. Model usage and pricing are recorded as soon as a model
response is available, before output guardrails, tools, or approval handling.
Tool batches remain sequential; assistant calls and predecessor results are
persisted before an approval pause. Completion and failure paths retain their
separate commit and rollback behavior.

`ExecutionContext` carries tree-wide counters and deadlines across child runs.
`RuntimeAccounting` stores usage and cost for each run; the two are separate
records with separate purposes.

## Entry points and verification

`run()` calls provider `generate()` and may resume a persisted approval batch.
`stream()` calls provider `stream()`, checks its final response against emitted
text, buffers output through guardrails, and yields the existing SSE event
sequence. Both entrypoints use the same context, accounting, guardrail, and tool
semantics without sharing one transport loop.

Run unit and API tests with `pytest`, plus `ruff check apps/api tests` and
`mypy apps/api/app`. Runtime persistence integration tests use a migrated,
isolated PostgreSQL/pgvector database configured with
`VF_TEST_DATABASE_URL`; its database name must end in `_test`. Run those tests
with `pytest tests/integration`.

## Plan-and-execute strategy

Published runtime configuration may select `REACTIVE` or `PLAN_AND_EXECUTE`.
Historical version snapshots without a strategy remain reactive through
application defaults. Planning configuration and its allowlisted working-state
schema are separate from the shared execution budget. The server validates the
schema locally and snapshots all settings into the immutable version.

Plan-and-execute runs apply conservative runtime ceilings even to older
published versions: 12 tool calls per run, 24 model calls, 52 steps, 80,000
tokens, and five minutes. A single task can use at most six tool calls. When a
task or run reaches its tool-call limit, the runtime removes tools from the
next model request and asks for a bounded summary; remaining work is reported
as partial where possible. These ceilings prevent repeated source discovery
from exhausting the larger legacy template budgets.

`PlanAndExecute` is an orchestration strategy under the existing `AgentRuntime`
facade and existing Run identity. It uses the normal provider, guardrail, tool,
budget, accounting and lifecycle collaborators. Its planner, task-result,
progress-assessment and synthesis calls use strict structured output. Plans,
tasks, sanitized state and safe progress events are persisted independently;
task execution is sequential and replan currently appends validated tasks.
The built-in Deep Research template creates an ordinary editable draft with
versioned template metadata and pins the workspace's immutable web search and
resource-reader tool versions.

Plan-and-execute is currently **inline and synchronous**. PostgreSQL job type,
checkpoint and fencing fields reserve the durable-job boundary, but async run
creation, worker resume, replaying SSE, durable cancellation, artifact APIs and
grounded citation rendering are not implemented. Do not enable async execution
or describe this strategy as restart-resumable until those lifecycle guarantees
and their integration tests are in place. See ADR-015 for the strategy and
compatibility decision.
