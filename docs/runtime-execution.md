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

The Playground now queues `PLAN_AND_EXECUTE` runs through the existing
PostgreSQL leased-job worker. Queued Run, user message, trace, initial event,
idempotency metadata and the versioned immutable request snapshot commit in one
transaction. The worker applies the input guardrail before model or tool calls.
The execution deadline starts when the first worker claims the Run, so queue
wait does not consume the budget. Async creation requires an
`Idempotency-Key`; repeating the same key and payload returns the same Run,
while reusing it for different input returns a conflict. Async runs are gated
by `VF_ENABLE_ASYNC_AGENT_RUNS` (off in application defaults, on in local
Docker Compose).

The worker increments `Run.execution_epoch` on acquisition. Runtime persistence
checks both that epoch and the current job lease owner before critical writes;
a stale worker cannot complete or fail a Run after takeover. Cancellation is a
durable request that the worker polls during provider and tool waits. Run
events are append-only and can be listed or replayed with
`GET /v1/runs/{id}/events:stream` and `Last-Event-ID`; disconnecting only stops
observation.

Checkpoints currently resume at verified boundaries. A task whose tool results
and conversation are checkpointed as `TASK_READY` continues without repeating
those calls; completed tasks remain completed, and a checkpoint between a
completed task and its assessment resumes by assessing that task. If a worker
stops during a model call, during a tool call before its result is checkpointed,
or at another ambiguous operation boundary, recovery fails the Run with
`RUN_RESUME_UNSAFE` rather than replaying work and risking duplicate cost or
side effects. Timeout accounting starts when the first worker claims the Run,
not while it waits in the queue.

Research outputs now use the generic `artifacts` store. Successful
`fetch_web_resource` calls persist a redacted `SOURCE_DOCUMENT` snapshot, bind it
to the current plan task, and expose only its artifact ID plus the inspected
excerpt to the model. Content up to 64 KiB stays inline; larger content uses the
configured private BlobStore and a deterministic content key. Artifacts are
deduplicated by run and producer key. The authenticated run artifact endpoints
list metadata and return bounded UTF-8 content ranges without exposing a storage
URI. Deep Research template v2 includes the run-scoped `read_artifact_content`
tool; template v1 remains materializable with its original tool set.

The API exposes `GET /v1/runs/{run_id}/artifacts` and
`GET /v1/runs/{run_id}/artifacts/{artifact_id}/content?offset=0&limit=16000`.
The latter returns a character range and a next offset. Both endpoints verify
workspace access and require the artifact to belong to the requested Run.

Research synthesis receives a bounded catalog of inspected source excerpts. A
citation is kept only when its source ID belongs to this Run and its exact
excerpt appears both in the stored source snapshot and the excerpt sent to the
model. The runtime makes one budgeted citation-repair call for semantic citation
errors; unresolved citations are removed and make the report `PARTIAL`. The
renderer adds source links and references from source artifacts to the final
`REPORT` artifact. This validates citation provenance, not factual correctness.
The deterministic Cloud Run versus ECS Fargate fixture covers a follow-up gap,
source-backed citations, invalid excerpts and report rendering without live
internet or model calls.

The PostgreSQL integration test for queue creation/idempotency requires
`VF_TEST_DATABASE_URL` and is skipped when that isolated test database is not
configured. Full failure-injection coverage for lease races, cancellation races
and every checkpoint boundary is still required before treating crash recovery
as fully validated. See ADR-015 for the strategy and compatibility decision.
