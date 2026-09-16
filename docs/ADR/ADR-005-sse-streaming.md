# ADR-005: Server-Sent Events for Streaming

- Status: Accepted
- Date: 2026-09-15

The MVP uses Server-Sent Events for agent output and runtime events. SSE fits one-way server-to-client execution streams and avoids WebSocket operational complexity until bidirectional interaction is proven necessary.

