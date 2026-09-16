# ADR-004: Framework-Agnostic Agent Domain

- Status: Accepted
- Date: 2026-09-15

VibesFactory owns its Agent, AgentVersion, Run, Tool, Workflow and runtime contracts. Vendor SDKs and optional frameworks are adapters; they must not become the platform domain model.

