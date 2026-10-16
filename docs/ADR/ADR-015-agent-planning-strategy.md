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

The initial strategy implementation runs inline. Durable async execution must
reuse the existing PostgreSQL leased queue and Run identity, and must not be
exposed until checkpoint recovery, execution fencing, cancellation and event
replay are implemented and tested. Research citations must resolve to stored,
inspected source snapshots; search highlights alone are not evidence.

## Consequences

- Existing reactive agents and historical versions remain compatible.
- Generic runtime orchestration owns no research-specific entities.
- Deep Research can use generic planning and web tools without bypassing normal
  publication, authorization or immutable-version rules.
- Async recovery, source artifacts, citation rendering and production rollout
  remain gated work; inline execution does not provide restart-resume semantics.

## Validation

Unit tests cover legacy defaults, local schema validation, task dependency and
state mutation rules, tool resource limits and template defaults. Full
acceptance also requires PostgreSQL failure-injection tests, async worker
recovery and cancellation tests, citation provenance tests, and keyboard and
responsive UI checks before enabling the feature for production use.
