# ADR-015: Generic plan-and-execute agent strategy

- Status: Accepted
- Date: 2026-10-13

## Context

VibesFactory needs multi-step agents without coupling agent behavior to a
research-only runtime or changing the established AgentVersion and Run
lifecycle. Existing provider, tool, guardrail, budget, accounting and tracing
contracts already provide the execution boundary. Historical published
versions must continue to behave as they did when they were created.

## Decision

Add `PLAN_AND_EXECUTE` as an opt-in strategy alongside `REACTIVE`. Missing
strategy fields in historical snapshots resolve to `REACTIVE` in the
application layer. Planning settings and a locally validated working-state
schema are immutable version configuration, separate from execution budgets.

Keep `AgentRuntime` as the facade and run planner, tasks, assessment, replan and
synthesis under one existing Run. Persist plan, tasks, business state and safe
progress events separately. Task execution is sequential. Model proposals are
validated by the application before plan or state mutation; state operations
only set or append declared top-level fields. Planning calls use strict
structured output and consume the same budget/accounting as ordinary calls.

Provide Deep Research as a versioned built-in template that materializes an
ordinary editable AgentDraft, runtime configuration and immutable built-in tool
bindings. Publishing remains explicit. New template revisions apply only to
new drafts; existing versions and runs are unchanged.

The initial strategy implementation runs inline. Durable async execution
reuses the existing PostgreSQL leased queue and Run identity. It remains behind
`VF_ENABLE_ASYNC_AGENT_RUNS` outside local Docker Compose until the remaining
failure-injection and approval-resume tests are complete. Research citations
must resolve to stored, inspected source snapshots; search highlights alone
are not evidence.

The first async implementation uses one leased `AGENT_EXECUTION` job per Run,
freezes the request snapshot, and fences runtime writes with both the Run's
execution epoch and the job lease owner. It resumes completed tasks and
`TASK_READY` checkpoints after tool results. Ambiguous in-flight model or tool
operations fail closed with `RUN_RESUME_UNSAFE`; the worker never blindly
replays them. Cancellation is persisted on the Run and durable events support
`Last-Event-ID` replay. The Playground observes the Run and plan through
polling, so closing the page does not cancel execution.

## Consequences

- Existing reactive agents and historical versions remain compatible.
- Generic runtime orchestration owns no research-specific entities.
- Deep Research can use generic planning and web tools without bypassing normal
  publication, authorization or immutable-version rules.
- Async recovery now has safe task-boundary resume and in-flight fail-closed
  behavior; failure-injection coverage and approval-continuation recovery still
  need PostgreSQL integration tests.
- Source snapshots, run-scoped artifact inspection, report artifacts, citation
  provenance validation and a deterministic offline research fixture are
  implemented. Production rollout and full PostgreSQL failure-injection
  coverage remain follow-up work; async execution is enabled by default only in
  local Docker Compose.

## Validation

Unit tests cover legacy defaults, local schema validation, task dependency and
state mutation rules, tool resource limits and template defaults. A PostgreSQL
integration test covers async queue creation and idempotency when
`VF_TEST_DATABASE_URL` is configured. Full acceptance also requires
failure-injection tests for worker recovery, fencing and cancellation,
PostgreSQL artifact persistence checks, and keyboard and responsive UI checks
before enabling the feature for production use.
