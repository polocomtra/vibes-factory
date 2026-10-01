# ADR-013: Per-call model accounting and effective-dated pricing

- Status: Accepted for Phase 17
- Date: 2026-10-01

## Decision

Each real provider request is represented by one MODEL span with its own
reported or estimated token usage, provider-call duration, and effective-dated
pricing snapshot. The runtime persists usage and duration immediately after a
response, before output guardrails, tool execution, or approval handling. Run
usage and estimated cost are recalculated from that run's MODEL spans; the
shared `ExecutionContext` remains the cumulative execution-budget counter for
workflow and child-run trees. Synthetic approval spans are not model calls.

The global PostgreSQL pricing registry is populated only through operator CLI
commands. A call stores its selected pricing ID and rates so future registry
edits cannot change its historical estimate. Missing usage or pricing remains
unknown, while known portions are retained as subtotals.

Monitoring excludes evaluation runs and their descendants. Legacy runs remain
in run counts, status rates, and run latency, while usage and cost aggregates
include only verifiable per-call accounting. API responses and chart points
carry coverage/completeness so consumers can distinguish a known subtotal from
a complete estimate.

## Consequences

- Budget enforcement continues to use tree-wide counters without inflating
  per-run token totals across parent and child runs.
- Approval continuation adds new provider-call spans to the original run and
  leaves prior call snapshots intact.
- Cost is an estimate in USD, not provider billing data; absent registry rates
  never fall back silently to environment pricing.
- Monitoring can query operational PostgreSQL directly in v1; alerts,
  warehouse pipelines, and external telemetry export remain deferred.
