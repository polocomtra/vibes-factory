"use client";

import {
  CheckCircle2,
  CircleAlert,
  Clock3,
  Maximize2,
  GitBranch,
  LoaderCircle,
  Radio,
  RefreshCw,
  StopCircle,
  X,
} from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ApprovalDecisionCard } from "./approval-decision-card";
import { apiFetch, readApiError } from "../lib/api";
import {
  fetchWorkflowNodeRuns,
  fetchWorkflowRun,
  fetchRunChildren,
  type ChildRun,
  type WorkflowEvent,
  type WorkflowNodeRun,
  type WorkflowRun,
} from "../lib/workflows";

type NodeStatus = WorkflowNodeRun["status"];

function statusIcon(status: string) {
  if (status === "COMPLETED") return <CheckCircle2 size={15} />;
  if (status === "FAILED") return <CircleAlert size={15} />;
  if (status === "CANCELLED") return <StopCircle size={15} />;
  return <LoaderCircle size={15} className="spin" />;
}

function readableEvent(event: string) {
  return event.replaceAll(".", " · ");
}

function jsonText(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function humanizeKey(key: string) {
  return key
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function findMarkdown(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (!isRecord(value)) return null;
  for (const key of ["markdown", "text", "content", "value"]) {
    if (typeof value[key] === "string") return value[key] as string;
  }
  return isRecord(value.output) ? findMarkdown(value.output) : null;
}

function TraceValue({ value }: { value: unknown }): ReactNode {
  if (value == null || value === "") return <span className="workflow-trace-empty-value">Not provided</span>;
  if (Array.isArray(value)) {
    return <div className="workflow-trace-list">{value.map((item, index) => <div key={index} className="workflow-trace-list-item"><TraceValue value={item} /></div>)}</div>;
  }
  if (isRecord(value)) {
    return <div className="workflow-trace-field-list">{Object.entries(value).map(([key, item]) => <div className="workflow-trace-field" key={key}><span>{humanizeKey(key)}</span><TraceValue value={item} /></div>)}</div>;
  }
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  return <span className="workflow-trace-value">{String(value)}</span>;
}

function traceMetadata(value: unknown, markdown: string | null) {
  if (!isRecord(value)) return [];
  const hiddenKeys = markdown ? new Set(["markdown", "text", "content", "value", "output"]) : new Set<string>();
  return Object.entries(value).filter(([key]) => !hiddenKeys.has(key));
}

function TracePayloadSection({ title, value, compact = false, onExpand }: { title: string; value: unknown; compact?: boolean; onExpand?: (title: string, markdown: string) => void }) {
  const markdown = findMarkdown(value);
  // Structured payloads are already rendered by TraceValue. Metadata cards are
  // only supplemental when a payload has a readable markdown response; using
  // both views for the same object duplicates fields such as `topic`.
  const metadata = markdown ? traceMetadata(value, markdown) : [];
  return <section className={`workflow-trace-data-section${compact ? " compact" : ""}`}>
    <div className="workflow-trace-data-heading"><div><h4>{title}</h4><small>{markdown ? "Readable response" : "Structured details"}</small></div>{markdown && onExpand ? <button className="icon-button workflow-output-expand" type="button" aria-label={`Expand ${title.toLowerCase()} output`} title="Expand output" onClick={() => onExpand(title, markdown)}><Maximize2 size={15} aria-hidden="true" /></button> : null}</div>
    <div className="workflow-trace-data-scroll">
      {markdown ? <article className="workflow-trace-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{markdown}</ReactMarkdown></article> : <TraceValue value={value} />}
    </div>
    {metadata.length > 0 ? <div className="workflow-trace-metadata">{metadata.map(([key, item]) => <div className="workflow-trace-metadata-card" key={key}><span>{humanizeKey(key)}</span><TraceValue value={item} /></div>)}</div> : null}
  </section>;
}

function TraceUsageSection({ usage }: { usage: Record<string, unknown> }) {
  const entries = Object.entries(usage);
  return <section className="workflow-trace-data-section compact"><div className="workflow-trace-data-heading"><div><h4>Usage</h4><small>Model consumption for this node</small></div></div>{entries.length > 0 ? <div className="workflow-trace-usage-grid">{entries.map(([key, value]) => <div key={key}><span>{humanizeKey(key)}</span><strong>{String(value)}</strong></div>)}</div> : <div className="workflow-trace-empty-value">No usage data available</div>}</section>;
}

function outputMarkdown(output: Record<string, unknown> | null) {
  if (!output) return "";
  if (Object.keys(output).length === 0) return "";
  for (const key of ["markdown", "text", "content", "value"]) {
    const value = output[key];
    if (typeof value === "string") return value;
  }
  return `\`\`\`json\n${jsonText(output)}\n\`\`\``;
}

function tokenCount(usage: Record<string, unknown>) {
  const value = usage.total_tokens ?? usage.output_tokens ?? usage.input_tokens;
  return typeof value === "number" || typeof value === "string" ? String(value) : "—";
}

function finalNodeStatus(
  event: WorkflowEvent,
  nodeRunsById: Map<string, WorkflowNodeRun>,
): NodeStatus | null {
  if (event.node_run_id) {
    return nodeRunsById.get(event.node_run_id)?.status ?? null;
  }
  const status = event.data.status;
  return typeof status === "string" ? (status as NodeStatus) : null;
}

function timelineStatus(event: WorkflowEvent, nodeStatus: NodeStatus | null): NodeStatus {
  if (nodeStatus) return nodeStatus;
  if (["workflow.failed", "workflow.node_failed"].includes(event.event) || event.event.includes("failed")) return "FAILED";
  if (event.event.includes("cancelled")) return "CANCELLED";
  // Lifecycle events are milestones, not active work. Once emitted, their
  // spinner must not remain visible just because the overall run is still open.
  if (["workflow.queued", "workflow.started", "workflow.completed"].includes(event.event) || event.event.includes("completed")) return "COMPLETED";
  return "RUNNING";
}

function formatDuration(durationMs: number | null) {
  if (durationMs == null) return "—";
  const seconds = durationMs / 1000;
  return `${seconds < 10 ? seconds.toFixed(2) : seconds.toFixed(1)} s`;
}

export function WorkflowRunView({ runId, onSelectNode, onNodeRunsChange, selectedNodeKey, onClearNodeFilter }: { runId: string; onSelectNode?: (nodeKey: string) => void; onNodeRunsChange?: (nodeRuns: WorkflowNodeRun[]) => void; selectedNodeKey?: string | null; onClearNodeFilter?: () => void }) {
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [nodeRuns, setNodeRuns] = useState<WorkflowNodeRun[]>([]);
  const [childRuns, setChildRuns] = useState<ChildRun[]>([]);
  const [childRunsError, setChildRunsError] = useState<string | null>(null);
  const [childRetryKey, setChildRetryKey] = useState(0);
  const [approvalRequestId, setApprovalRequestId] = useState<string | null>(null);
  const [selectedNodeRunId, setSelectedNodeRunId] = useState<string | null>(null);
  const [selectedChildRunId, setSelectedChildRunId] = useState<string | null>(null);
  const [expandedOutput, setExpandedOutput] = useState<{ title: string; markdown: string } | null>(null);
  const [connection, setConnection] = useState<"Connected" | "Reconnecting" | "Polling">("Reconnecting");
  const [error, setError] = useState<string | null>(null);
  const outputModalRef = useRef<HTMLElement>(null);
  const outputModalCloseRef = useRef<HTMLButtonElement>(null);
  const terminal = run ? ["COMPLETED", "FAILED", "CANCELLED"].includes(run.status) : false;

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const [nextRun, nextNodeRuns] = await Promise.all([
          fetchWorkflowRun(runId),
          fetchWorkflowNodeRuns(runId),
        ]);
        if (cancelled) return;
        setRun(nextRun);
        setNodeRuns(nextNodeRuns);
        onNodeRunsChange?.(nextNodeRuns);
        setError(null);
      } catch (reason: unknown) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load run.");
      }
    }
    void poll();
    const timer = window.setInterval(() => {
      if (!terminal) void poll();
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runId, terminal, onNodeRunsChange]);

  const childRunIds = nodeRuns.flatMap((item) => item.agent_run_id ? [item.agent_run_id] : []);
  const childRunKey = childRunIds.join(",");

  useEffect(() => {
    let cancelled = false;
    let retry = 0;
    let timer: number | undefined;

    async function loadChildren() {
      try {
        const ids = childRunKey ? childRunKey.split(",") : [];
        const nested = (await Promise.all(ids.map((agentRunId) => fetchRunChildren(agentRunId)))).flat();
        if (cancelled) return;
        setChildRuns(nested);
        setChildRunsError(null);
      } catch (reason: unknown) {
        if (cancelled) return;
        setChildRunsError(reason instanceof Error ? reason.message : "Unable to load child runs.");
        retry += 1;
        timer = window.setTimeout(loadChildren, Math.min(10_000, 1_000 * 2 ** Math.min(retry, 3)));
      }
    }

    setChildRunsError(null);
    if (!childRunKey) {
      setChildRuns([]);
      return () => { cancelled = true; };
    }
    void loadChildren();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [childRunKey, childRetryKey]);

  useEffect(() => {
    let cancelled = false;
    let cursor = 0;
    let retry = 0;
    async function connect() {
      try {
        setConnection("Reconnecting");
        const response = await apiFetch(`/v1/workflow-runs/${runId}/events`, {
          headers: { "Last-Event-ID": String(cursor) },
        });
        if (!response.ok || !response.body) throw new Error(await readApiError(response));
        setConnection("Connected");
        retry = 0;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!cancelled) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buffer += decoder.decode(chunk.value, { stream: true });
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";
          for (const block of blocks) {
            const dataLine = block.split("\n").find((line) => line.startsWith("data:"));
            if (!dataLine) continue;
            try {
              const event = JSON.parse(dataLine.slice(5)) as WorkflowEvent;
              cursor = event.sequence;
              if (
                event.event === "approval.required" &&
                typeof event.data.approval_request_id === "string"
              ) {
                setApprovalRequestId(event.data.approval_request_id);
              }
              setEvents((current) => {
                if (current.some((item) => item.sequence === event.sequence)) return current;
                return [...current, event].sort((left, right) => left.sequence - right.sequence);
              });
            } catch {
              // Ignore heartbeat and malformed non-data blocks.
            }
          }
        }
        if (!cancelled && !terminal) throw new Error("stream ended");
      } catch {
        if (!cancelled) {
          setConnection("Polling");
          retry += 1;
          window.setTimeout(() => void connect(), Math.min(8000, 500 * 2 ** Math.min(retry, 4)));
        }
      }
    }
    void connect();
    return () => {
      cancelled = true;
    };
  }, [runId, terminal]);

  const nodeRunsById = useMemo(
    () => new Map(nodeRuns.map((nodeRun) => [nodeRun.id, nodeRun])),
    [nodeRuns],
  );
  const failedNodeRun = nodeRuns.find(
    (nodeRun) => nodeRun.status === "FAILED" && nodeRun.node_key === run?.current_node_key,
  ) ?? nodeRuns.find((nodeRun) => nodeRun.status === "FAILED");
  const selectedNodeRun = selectedNodeRunId ? nodeRunsById.get(selectedNodeRunId) ?? null : null;

  useEffect(() => {
    if (!selectedNodeKey) return;
    const matchingRun = [...nodeRuns].reverse().find((item) => item.node_key === selectedNodeKey);
    if (matchingRun) setSelectedNodeRunId(matchingRun.id);
  }, [nodeRuns, selectedNodeKey]);
  const selectedChildRun = selectedChildRunId ? childRuns.find((item) => item.id === selectedChildRunId) ?? null : null;
  const elapsed = useMemo(
    () => run?.started_at
      ? Math.max(0, Math.round(((run.completed_at ? new Date(run.completed_at).getTime() : Date.now()) - new Date(run.started_at).getTime()) / 1000))
      : 0,
    [run],
  );
  const completedNodes = nodeRuns.filter((nodeRun) => nodeRun.status === "COMPLETED").length;
  const markdown = outputMarkdown(run?.output ?? null);

  useEffect(() => {
    if (!expandedOutput) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const dialog = outputModalRef.current;
    document.body.style.overflow = "hidden";
    const frame = window.requestAnimationFrame(() => outputModalCloseRef.current?.focus());
    function handleDialogKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setExpandedOutput(null);
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled), [href], [tabindex]:not([tabindex="-1"])'));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleDialogKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleDialogKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus({ preventScroll: true });
    };
  }, [expandedOutput]);

  if (!run) return <section className="panel agent-state"><LoaderCircle className="spin" size={18} />Loading run…</section>;

  return (
    <div className="workflow-run-view">
      <div className="workflow-run-summary" role="status" aria-live="polite">
        <div>
          <span className={`run-status-dot ${run.status.toLowerCase()}`} />
          <strong>{run.status}</strong>
          <span className="workflow-live-state"><Radio size={13} />{connection}</span>
        </div>
        <div className="workflow-run-metrics">
          <span><Clock3 size={14} />{elapsed}s</span>
          <span><GitBranch size={14} />{completedNodes}/{nodeRuns.length || "—"} nodes</span>
          <span>Tokens {String(run.usage.total_tokens ?? "—")}</span>
        </div>
      </div>

      {run.status === "WAITING_APPROVAL" && approvalRequestId ? (
        <ApprovalDecisionCard approvalId={approvalRequestId} />
      ) : null}

      {error ? <div className="form-error agent-alert" role="alert">{error}</div> : null}

      <section className="workflow-output-panel" aria-labelledby="workflow-output-heading">
        <div className="workflow-output-header">
          <div>
            <span className="eyebrow">Workflow result</span>
            <h2 id="workflow-output-heading">Output</h2>
          </div>
          <div className="workflow-output-header-actions">
            {run.status === "COMPLETED" ? <span className="status-badge success"><span />Ready</span> : <span className="status-badge muted">{run.status === "RUNNING" ? "Generating" : "Waiting"}</span>}
            {markdown ? <button className="icon-button workflow-output-expand" type="button" aria-label="Expand workflow output" title="Expand output" onClick={() => setExpandedOutput({ title: "Workflow output", markdown })}><Maximize2 size={15} aria-hidden="true" /></button> : null}
          </div>
        </div>
        {markdown ? (
          <article className="workflow-output-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{markdown}</ReactMarkdown>
          </article>
        ) : (
          <div className="workflow-output-empty">
            <LoaderCircle size={17} className={run.status === "RUNNING" ? "spin" : ""} />
            <span>{run.status === "COMPLETED" && isRecord(run.output) && Object.keys(run.output).length === 0
              ? "The workflow completed with an empty result. Set the End node’s Final output to a previous node’s result, then publish and rerun."
              : run.status === "COMPLETED"
                ? "The workflow completed without a renderable output."
                : "The final response will appear here when the workflow completes."}</span>
          </div>
        )}
      </section>

      <section className="workflow-run-layout">
        <div className="workflow-run-timeline">
          <div className="panel-heading">
            <div><span className="eyebrow">Live observation</span><h2>Execution timeline</h2></div>
            {selectedNodeKey ? <button className="button subtle-button" type="button" onClick={onClearNodeFilter}>Clear node filter</button> : null}
            {terminal ? <span className="status-badge muted">Terminal</span> : <span className="status-badge success"><span />Live</span>}
          </div>
          {events.length === 0 ? (
            <div className="workflow-empty-timeline"><RefreshCw size={19} /><p>Waiting for the worker to emit the first event…</p></div>
          ) : (
            <ol className="workflow-timeline">
              {events.map((event) => {
                const eventParentRunId = typeof event.data.parent_run_id === "string" ? event.data.parent_run_id : null;
                let nodeRun = event.node_run_id ? nodeRunsById.get(event.node_run_id) ?? null : null;
                if (!nodeRun && eventParentRunId) {
                  const rootNode = nodeRuns.find((item) => item.agent_run_id === eventParentRunId);
                  const nestedRun = childRuns.find((child) => child.id === eventParentRunId);
                  nodeRun = rootNode ?? (nestedRun ? nodeRuns.find((item) => item.agent_run_id === nestedRun.root_run_id) ?? null : null);
                }
                if (selectedNodeKey && nodeRun?.node_key !== selectedNodeKey) return null;
                const nodeStatus = finalNodeStatus(event, nodeRunsById);
                const visualStatus = timelineStatus(event, nodeStatus);
                const label = String(event.data.node_name ?? nodeRun?.node_name ?? event.data.node_key ?? readableEvent(event.event));
                const content = (
                  <>
                    <div className="workflow-timeline-marker">{statusIcon(visualStatus)}</div>
                    <div className="workflow-timeline-content">
                      <div><strong>{label}</strong><span className="timeline-time">{new Date(event.occurred_at).toLocaleTimeString()}</span></div>
                      <p>{readableEvent(event.event)}{event.data.code ? ` · ${String(event.data.code)}` : ""}</p>
                      {nodeRun?.duration_ms != null ? <small>{formatDuration(nodeRun.duration_ms)} · {nodeStatus ?? nodeRun.status}</small> : null}
                    </div>
                  </>
                );
                return (
                    <li key={event.sequence} className={`workflow-timeline-item workflow-${visualStatus.toLowerCase()}`}>
                    {nodeRun ? <button type="button" className={`workflow-trace-button${selectedNodeRunId === nodeRun.id ? " selected" : ""}`} onClick={() => { setSelectedNodeRunId(nodeRun.id); onSelectNode?.(nodeRun.node_key); }} aria-label={`Inspect ${label} trace`} aria-current={selectedNodeRunId === nodeRun.id ? "true" : undefined}>{content}</button> : content}
                  </li>
                );
              })}
            </ol>
          )}
        </div>

        <aside className="workflow-run-inspector">
          <section className="workflow-run-details">
            <div className="workflow-inspector-section-heading"><div><span className="panel-label">Run details</span><h3>Workflow run</h3></div></div>
            <dl>
              <div><dt>Run ID</dt><dd><code>{run.id.slice(0, 8)}…</code></dd></div>
              <div><dt>Trace</dt><dd><code>{run.trace_id.slice(0, 8)}…</code></dd></div>
              <div><dt>Version</dt><dd><code>{run.workflow_version_id.slice(0, 8)}…</code></dd></div>
              <div><dt>Current node</dt><dd>{run.current_node_name || "—"}</dd></div>
            </dl>
            {run.error ? <div className="workflow-error-box"><StopCircle size={15} /><div><strong>{run.error.code}</strong><p>{run.error.message}</p>{failedNodeRun?.error && typeof failedNodeRun.error.budget === "string" ? <p><strong>{humanizeKey(failedNodeRun.error.budget)}</strong>: {String(failedNodeRun.error.used ?? "—")} / {String(failedNodeRun.error.limit ?? "—")} used. Increase this limit under Run budget, then publish a new workflow version.</p> : null}</div></div> : null}
            <TracePayloadSection title="Workflow input" value={run.input} compact />
            <section className="workflow-child-runs" aria-labelledby="workflow-child-runs-heading">
              <div className="workflow-inspector-section-heading"><div><span className="panel-label">Multi-agent</span><h3 id="workflow-child-runs-heading">Child runs</h3></div><span className="status-badge muted">{childRuns.length}</span></div>
              {childRunsError ? <div className="workflow-child-runs-error" role="status"><span>Child-run details are temporarily unavailable. The workflow result is unaffected.</span><button className="text-button" type="button" onClick={() => { setChildRunsError(null); setChildRetryKey((key) => key + 1); }}>Retry</button></div> : null}
              {!childRunsError && childRuns.length === 0 ? <p className="workflow-inspector-hint">No direct child runs have been emitted yet.</p> : null}
              {childRuns.length > 0 ? <div className="workflow-child-run-list">{childRuns.map((child) => <button type="button" className={`workflow-child-run${selectedChildRunId === child.id ? " selected" : ""}`} key={child.id} onClick={() => setSelectedChildRunId(child.id)}><span className={`run-status-dot ${child.status.toLowerCase()}`} /><span><strong>{child.status}</strong><small>Depth {child.agent_depth} · parent {child.parent_run_id?.slice(0, 8) ?? "—"} · root {child.root_run_id.slice(0, 8)}…</small></span><code>{child.id.slice(0, 8)}…</code></button>)}</div> : null}
              {selectedChildRun ? <div className="workflow-child-run-detail"><div><span>Child run</span><code>{selectedChildRun.id}</code></div><div><span>Trace</span><code>{selectedChildRun.trace_id}</code></div><div><span>Agent version</span><code>{selectedChildRun.agent_version_id}</code></div><TraceUsageSection usage={selectedChildRun.usage} />{selectedChildRun.error ? <div className="workflow-error-box"><CircleAlert size={15} /><div><strong>{selectedChildRun.error.code}</strong><p>{selectedChildRun.error.message}</p></div></div> : null}</div> : null}
            </section>
          </section>

          {selectedNodeRun ? (
            <section className="workflow-trace-panel" aria-labelledby="workflow-trace-detail-heading">
              <div className="workflow-trace-detail">
                <div className="workflow-inspector-section-heading">
                  <div><span className="panel-label">Selected trace</span><h3 id="workflow-trace-detail-heading">{selectedNodeRun.node_name}</h3></div>
                  <button type="button" className="icon-button" aria-label="Close trace details" onClick={() => setSelectedNodeRunId(null)}><X size={15} /></button>
                </div>
                <div className="workflow-trace-stats">
                  <span><small>Status</small><strong>{selectedNodeRun.status}</strong></span>
                  <span><small>Duration</small><strong>{formatDuration(selectedNodeRun.duration_ms)}</strong></span>
                  <span><small>Tokens</small><strong>{tokenCount(selectedNodeRun.usage)}</strong></span>
                </div>
                <TracePayloadSection title="Input" value={selectedNodeRun.input} />
                <TracePayloadSection title="Output" value={selectedNodeRun.output} onExpand={(title, content) => setExpandedOutput({ title: `${selectedNodeRun.node_name} · ${title}`, markdown: content })} />
                <TraceUsageSection usage={selectedNodeRun.usage} />
                {selectedNodeRun.error ? <div className="workflow-error-box"><CircleAlert size={15} /><div className="workflow-trace-error-copy"><strong>Node error</strong><div><TraceValue value={selectedNodeRun.error} /></div></div></div> : null}
              </div>
            </section>
          ) : <section className="workflow-trace-panel"><p className="workflow-inspector-hint">Select a node event to inspect its input, output, usage and duration.</p></section>}
        </aside>
      </section>
      {expandedOutput ? <div className="trace-modal-backdrop workflow-output-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setExpandedOutput(null); }}>
        <section className="workflow-output-modal" role="dialog" aria-modal="true" aria-labelledby="workflow-expanded-output-title" ref={outputModalRef}>
          <header className="workflow-output-modal-header"><div><span className="eyebrow">Expanded output</span><h2 id="workflow-expanded-output-title">{expandedOutput.title}</h2></div><button ref={outputModalCloseRef} className="icon-button" type="button" aria-label="Close expanded output" onClick={() => setExpandedOutput(null)}><X size={17} aria-hidden="true" /></button></header>
          <div className="workflow-output-modal-body"><article className="workflow-output-markdown workflow-output-expanded-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={{ table: ({ children }) => <div className="workflow-output-table-scroll" role="region" aria-label="Scrollable output table" tabIndex={0}><table>{children}</table></div> }}>{expandedOutput.markdown}</ReactMarkdown></article></div>
        </section>
      </div> : null}
    </div>
  );
}
