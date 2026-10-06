# ADR-010 — BYOK Credential Architecture

## Status

Accepted

## Context

HTTP tools, MCP servers and model providers need workspace-scoped credentials,
but secrets must remain separate from agents, immutable tool versions, model
messages and product traces. PostgreSQL remains the system of record, while the
runtime must resolve credentials only at the executor boundary.

## Decision

Phase 7 stores credential payloads as JSON encrypted with the `cryptography`
library using AES-GCM. The backend reads a 32-byte URL-safe base64 master key
from `VF_ENCRYPTION_MASTER_KEY`; the database stores ciphertext and a key version,
never plaintext. A workspace-scoped resolver checks ownership and revocation
before decrypting.

The resolver returns decrypted material only to the relevant executor. HTTP
tools may inject a selected secret field into one outbound header through a
non-secret `credential_binding` template. Resolved secret values are supplied
to the centralized redactor before tool output, traces or logs are persisted.

Model Connections add a workspace-owned metadata record referencing one vault
credential. Supported providers are Azure OpenAI, Gemini, DeepSeek and
OpenRouter. Creating a connection and its encrypted `api_key` credential is one
database transaction. Provider and endpoint are immutable; rename and key
rotation are supported, while revocation disables the credential and preserves
the connection reference for historical agent versions. Only workspace owners
may create, rename, rotate or revoke connections.

Agent drafts may bind to a connection and model. A published AgentVersion pins
the connection ID, credential ID, provider, endpoint, model/deployment and
known capabilities, never the key. The shared runtime resolver checks tenant
scope and revocation before every model call, decrypts only in memory and passes
the key to a per-call provider adapter. A rotated key applies to later calls
without republishing. A revoked or invalid BYOK connection fails explicitly and
never falls back to the platform credential. Existing agents retain the system
Azure `gpt-6-luna` default.

Google Secret Manager, master-key rotation, OAuth and per-user credentials are
deferred to later milestones. BYOK for embeddings and custom provider proxies
are also out of scope.

## Consequences

- Credential references remain safe to store in tool configuration and
  AgentVersion snapshots.
- Published model bindings remain stable when a draft changes, while key
  rotation remains operational without changing immutable snapshots.
- A workspace member can use an owner-managed connection through existing agent
  permissions, but cannot mutate the key.
- Owner-only credential mutation limits the blast radius of secret changes.
- A production deployment must provision `VF_ENCRYPTION_MASTER_KEY` securely.
- Future key rotation can use `key_version` without changing the public API.
