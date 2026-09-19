# ADR-011: PostgreSQL leased queue for local knowledge ingestion

## Status

Accepted for Phase 9 MVP.

## Decision

Knowledge ingestion jobs are durable PostgreSQL rows claimed by a separate
worker with `FOR UPDATE SKIP LOCKED`, heartbeat leases and bounded retries.
`JobDispatcher` is the application boundary; a future Cloud Tasks adapter can
replace dispatch without changing document or API contracts. The `jobs` table
remains the audit/status source of truth.

## Trade-off

This is lower-throughput than Redis/Celery, but keeps local Compose
reproducible, survives worker restarts and adds no mandatory infrastructure.
Cloud Tasks is deferred until deployment hardening.
