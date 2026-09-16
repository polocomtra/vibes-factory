# ADR-008: OpenTelemetry-Compatible Tracing

- Status: Accepted
- Date: 2026-09-15

VibesFactory stores its own trace/span records for the product Trace Viewer and initializes OpenTelemetry-compatible instrumentation for future export. `run_id`, `trace_id` and `parent_span_id` remain first-class correlation fields.

