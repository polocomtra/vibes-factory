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
