# ADR-007: Separate Session, Memory and Workflow State

- Status: Accepted
- Date: 2026-09-15

Session messages represent active conversation history. Memory represents selected durable facts. Workflow state represents persisted graph execution progress. These concerns have different lifecycles and must not be collapsed into one JSON or message store.

