# ADR-002: PostgreSQL as System of Record

- Status: Accepted
- Date: 2026-09-15

PostgreSQL stores durable platform state, transactions and audit-relevant history. Redis is disposable operational infrastructure and must never be the authoritative source for business resources, runs, sessions, workflow state or evaluations.

