# ADR-010 — BYOK Credential Architecture

## Status

Accepted

## Context

HTTP tools and future integrations need workspace-scoped provider credentials,
but secrets must remain separate from agents, immutable tool versions, model
messages and product traces. PostgreSQL remains the system of record, while the
runtime must resolve credentials only at the executor boundary.

## Decision

Phase 7 stores credential payloads as JSON encrypted with the `cryptography`
library using AES-GCM. The backend reads a 32-byte URL-safe base64 master key
from `VF_ENCRYPTION_MASTER_KEY`; the database stores ciphertext and a key version,
never plaintext. A workspace-scoped resolver checks ownership and revocation
before decrypting.

The resolver returns decrypted material only to the tool executor. HTTP tools may
inject a selected secret field into one outbound header through a non-secret
`credential_binding` template. Resolved secret values are supplied to the
centralized redactor before tool output, traces or logs are persisted.

Google Secret Manager, master-key rotation, OAuth and MCP credential adapters are
deferred to later milestones.

## Consequences

- Credential references remain safe to store in tool configuration and
  AgentVersion snapshots.
- Owner-only credential mutation limits the blast radius of secret changes.
- A production deployment must provision `VF_ENCRYPTION_MASTER_KEY` securely.
- Future key rotation can use `key_version` without changing the public API.
