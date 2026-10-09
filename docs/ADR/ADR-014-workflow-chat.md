# ADR-014: Conversational workflow invocation

- Status: Accepted
- Date: 2026-10-06

## Context

Workflow invocation currently requires navigating to a workflow, opening its Run form, and entering parameters. Users need a conversational entry point that can collect explicit inputs, show durable execution activity, and answer follow-up questions without weakening workflow authorization or runtime boundaries.

## Decision

Add chat to each workflow, backed by a published version's explicit `configuration.input_schema` and `configuration.chat` settings. Sessions pin one immutable version and are scoped to their workspace and creating user. A provider-independent structured model decision may ask, answer, or request execution; backend validation determines missing/default/invalid inputs, and only validated explicit execution intent can queue a run. Model calls never create runs or invoke tools directly.

The structured decision schema is generated from the pinned workflow input contract. Every candidate field is explicitly declared and nullable so the model can represent missing information while remaining compatible with strict provider JSON Schema requirements. Object and array candidates are transported as JSON text and parsed before workflow input validation.

Chat turns, messages, model usage, trace linkage and run-card references are durable PostgreSQL records. The leased worker uses idempotency and atomically persists the run, execution job and transcript association. Both manual and chat entry points use the shared run-creation service. Workflow execution, SSE, child runs and approval APIs remain the source of execution state.

The workflow detail page links to a per-workflow chat route. Desktop presents chat beside the read-only execution graph/timeline; smaller screens use Chat and Execution tabs. The run form shares the published input contract. Existing published versions remain unchanged and chat is enabled by publishing a new version.

## Consequences

- Existing versions and manual Run remain compatible.
- Chat cannot change workflow graphs or bypass HITL approvals.
- A session has at most one active interpretation turn and one nonterminal workflow run.
- Chat model usage is reported separately from workflow execution usage.
- Non-retryable provider request errors fail the chat turn immediately; transient provider failures use the job retry budget.
- Global workflow routing, public deployment, uploads, voice and parallel session runs remain out of scope.

## Validation

Validate schema behavior and intent decisions with a fake provider; exercise tenant isolation, idempotency, redelivery and run hydration against PostgreSQL; and verify responsive, keyboard-accessible UI in both themes.
