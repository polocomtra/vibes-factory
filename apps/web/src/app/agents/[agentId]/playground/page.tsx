"use client";

import {
  ArrowLeft,
  Bot,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  Copy,
  Database,
  FileText,
  GitBranch,
  LoaderCircle,
  Plus,
  Search as SearchIcon,
  Send,
  X,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import ReactMarkdown, { type Components } from "react-markdown";
import { createPortal } from "react-dom";
import { Children, isValidElement, type ReactElement, useCallback, useEffect, useMemo, useRef, useState } from "react";
import remarkGfm from "remark-gfm";

import { AppShell } from "../../../../components/app-shell";
import {
  createRunStream,
  createSession,
  fetchMessages,
  fetchRun,
  fetchSessions,
  fetchRunTrace,
  fetchSpan,
  fetchTraceSpans,
  type Message,
  type Run,
  type Session,
  type Span,
  type RunTrace,
  RuntimeApiError,
} from "../../../../lib/runtime";
import { fetchAgent, fetchVersions, type Agent, type AgentVersionSummary } from "../../../../lib/agents";

function dateLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function tokenLabel(value: number | undefined) {
  return value === undefined ? "—" : value.toLocaleString();
}

function StatusBadge({ status }: { status: string }) {
  const tone = status === "COMPLETED" ? "success" : status === "FAILED" ? "error" : status === "RUNNING" ? "info" : "muted";
  return <span className={`status-badge ${tone}`}><span aria-hidden="true" />{status.replaceAll("_", " ")}</span>;
}

function textOf(message: Message) {
  return message.content?.text ?? "";
}

type ToolExecutionResult = {
  ok: boolean;
  output?: unknown;
  error?: { code?: string; message?: string };
};

type ToolCallRecord = {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  createdAt: string;
  result?: ToolExecutionResult;
};

type ConversationItem =
  | { kind: "message"; message: Message; tools: ToolCallRecord[] }
  | { kind: "tools"; tools: ToolCallRecord[] };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseToolResult(message: Message): ToolExecutionResult {
  const embedded = message.content.output;
  if (isRecord(embedded) && typeof embedded.ok === "boolean") {
    return embedded as ToolExecutionResult;
  }

  const text = textOf(message);
  try {
    const parsed: unknown = JSON.parse(text);
    if (isRecord(parsed) && typeof parsed.ok === "boolean") return parsed as ToolExecutionResult;
  } catch {
    // Older messages may contain a plain text tool result.
  }
  return { ok: true, output: text || undefined };
}

function groupConversation(messages: Message[]): ConversationItem[] {
  const items: ConversationItem[] = [];
  const pendingTools: ToolCallRecord[] = [];
  const callsById = new Map<string, ToolCallRecord>();

  for (const message of messages) {
    if (message.role === "ASSISTANT" && message.content.type === "tool_calls") {
      for (const [index, call] of (message.content.tool_calls ?? []).entries()) {
        const record: ToolCallRecord = {
          id: call.id ?? message.id + "-tool-" + index,
          name: call.name,
          arguments: call.arguments,
          createdAt: message.created_at,
        };
        pendingTools.push(record);
        callsById.set(record.id, record);
      }
      continue;
    }

    if (message.role === "TOOL") {
      const toolCallId = typeof message.content.tool_call_id === "string" ? message.content.tool_call_id : null;
      const existing = toolCallId ? callsById.get(toolCallId) : undefined;
      if (existing) {
        existing.result = parseToolResult(message);
      } else {
        pendingTools.push({
          id: toolCallId ?? message.id,
          name: typeof message.content.name === "string" ? message.content.name : "tool",
          arguments: {},
          createdAt: message.created_at,
          result: parseToolResult(message),
        });
      }
      continue;
    }

    if (message.role === "ASSISTANT" && message.content.type === "text") {
      items.push({ kind: "message", message, tools: pendingTools.splice(0) });
      continue;
    }

    items.push({ kind: "message", message, tools: [] });
  }

  if (pendingTools.length > 0) items.push({ kind: "tools", tools: pendingTools });
  return items;
}

function toolResultLabel(tool: ToolCallRecord) {
  if (!tool.result) return "Running";
  if (!tool.result.ok) return "Failed";
  if (isRecord(tool.result.output) && Array.isArray(tool.result.output.results)) {
    const count = tool.result.output.results.length;
    return count + (count === 1 ? " result" : " results");
  }
  return "Completed";
}

function toolResultError(tool: ToolCallRecord) {
  const error = tool.result?.error;
  return isRecord(error) && typeof error.message === "string" ? error.message : "Tool execution failed.";
}

function ToolActivityGroup({ tools }: { tools: ToolCallRecord[] }) {
  const groups = tools.reduce<Array<{ name: string; calls: ToolCallRecord[] }>>((accumulator, tool) => {
    const key = tool.name.toLowerCase();
    const group = accumulator.find((item) => item.name.toLowerCase() === key);
    if (group) group.calls.push(tool);
    else accumulator.push({ name: tool.name, calls: [tool] });
    return accumulator;
  }, []);

  return <section className="inline-tool-activity" aria-label="Tool activity">
    <div className="inline-tool-activity-header">
      <SearchIcon size={13} aria-hidden="true" />
      <span>Tool activity</span>
      <span className="tool-activity-count">{tools.length} {tools.length === 1 ? "call" : "calls"}</span>
    </div>
    <div className="tool-activity-groups">
      {groups.map((group) => {
        const failedCount = group.calls.filter((call) => call.result && !call.result.ok).length;
        return <details className="tool-activity-group" key={group.name}>
          <summary>
            <span className="tool-group-icon"><SearchIcon size={13} aria-hidden="true" /></span>
            <span className="tool-group-copy"><strong>{group.name}</strong><small>{group.calls.length} {group.calls.length === 1 ? "invocation" : "invocations"}</small></span>
            <span className={"tool-group-status" + (failedCount > 0 ? " failed" : "")}>{failedCount > 0 ? failedCount + " failed" : "Completed"}</span>
            <ChevronDown className="tool-group-chevron" size={14} aria-hidden="true" />
          </summary>
          <div className="tool-call-list">
            {group.calls.map((tool, index) => {
              const query = typeof tool.arguments.query === "string" ? tool.arguments.query : JSON.stringify(tool.arguments);
              return <div className="tool-call-entry" key={tool.id}>
                <div className="tool-call-meta"><span>Call {index + 1}</span><code title={query}>{query}</code><span className={"tool-call-status" + (tool.result && !tool.result.ok ? " failed" : "")}>{toolResultLabel(tool)}</span></div>
                {tool.result && !tool.result.ok ? <p className="tool-call-output error">{toolResultError(tool)}</p> : null}
              </div>;
            })}
          </div>
        </details>;
      })}
    </div>
  </section>;
}

function CopyButton({ text, label = "Copy message" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return <button className="message-copy-button" type="button" onClick={() => void copy()} aria-label={copied ? `${label} copied` : label} title={copied ? "Copied" : label}><span aria-hidden="true">{copied ? <Check size={13} /> : <Copy size={13} />}</span><span className="sr-only">{copied ? "Copied" : "Copy"}</span></button>;
}

const markdownComponents: Components = {
  a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
  code: ({ children, className, ...props }) => <code className={className || "markdown-inline-code"} {...props}>{children}</code>,
  pre: ({ children }) => {
    const child = Children.toArray(children)[0];
    const codeElement = isValidElement(child) ? child as ReactElement<{ children?: unknown; className?: string }> : null;
    const language = codeElement?.props.className?.match(/language-(\w+)/)?.[1] ?? "code";
    const code = String(codeElement?.props.children ?? "").replace(/\n$/, "");
    return <div className="markdown-code-block"><div className="markdown-code-toolbar"><span>{language}</span><CopyButton text={code} label={`Copy ${language} block`} /></div><pre><code className={codeElement?.props.className}>{code}</code></pre></div>;
  },
};

function MessageContent({ message }: { message: Message }) {
  const content = textOf(message);
  return <div className="message-content"><ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{content}</ReactMarkdown></div>;
}

function PlaygroundMessage({ message, agentName, tools = [] }: { message: Message; agentName: string; tools?: ToolCallRecord[] }) {
  const content = textOf(message);
  if (message.role === "TOOL") return null;
  return <article className={`playground-message ${message.role.toLowerCase()}`}><div className="message-meta"><span>{message.role === "USER" ? "You" : message.role === "ASSISTANT" ? agentName : message.role}</span><div className="message-meta-actions"><time dateTime={message.created_at}>{dateLabel(message.created_at)}</time><CopyButton text={content} /></div></div>{tools.length > 0 ? <ToolActivityGroup tools={tools} /> : null}<MessageContent message={message} /></article>;
}

function TraceInspector({ runId, onClose }: { runId: string; onClose: () => void }) {
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [spans, setSpans] = useState<Span[]>([]);
  const [selected, setSelected] = useState<Span | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [portalReady, setPortalReady] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousBodyOverflow = document.body.style.overflow;
    const previousBodyPaddingRight = document.body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;

    document.body.style.overflow = "hidden";
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`;
    document.body.classList.add("trace-modal-open");
    setPortalReady(true);
    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.body.style.paddingRight = previousBodyPaddingRight;
      document.body.classList.remove("trace-modal-open");
      previouslyFocusedRef.current?.focus({ preventScroll: true });
      previouslyFocusedRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!portalReady) return;
    const focusFrame = window.requestAnimationFrame(() => closeButtonRef.current?.focus({ preventScroll: true }));
    return () => window.cancelAnimationFrame(focusFrame);
  }, [portalReady]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const runTrace = await fetchRunTrace(runId);
        const items = await fetchTraceSpans(runTrace.trace.id);
        if (cancelled) return;
        setTrace(runTrace); setSpans(items); setSelected(items[0] ?? null);
      } catch (reason: unknown) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load trace.");
      }
    })();
    return () => { cancelled = true; };
  }, [runId]);

  async function selectSpan(span: Span) {
    setSelected(span);
    try { setSelected(await fetchSpan(span.id)); }
    catch (reason: unknown) { setError(reason instanceof Error ? reason.message : "Unable to load span."); }
  }

  if (!portalReady) return null;

  return createPortal(
    <div className="trace-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="trace-inspector" role="dialog" aria-modal="true" aria-labelledby="trace-title">
        <header className="trace-inspector-header"><div><span className="panel-kicker">Observability</span><h2 id="trace-title">Run trace</h2><p className="panel-copy">Inspect the persisted execution timeline for <code>{runId.slice(0, 8)}…</code>.</p></div><button ref={closeButtonRef} className="icon-button" type="button" aria-label="Close trace inspector" onClick={onClose}><X size={17} aria-hidden="true" /></button></header>
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        {!trace ? <div className="trace-loading"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading trace…</div> : <div className="trace-split-view">
          <div className="trace-timeline" aria-label="Trace spans">
            <div className="trace-summary"><StatusBadge status={trace.trace.status} /><span>{spans.length} spans</span></div>
            {spans.map((span) => <button className={selected?.id === span.id ? "trace-span selected" : "trace-span"} type="button" key={span.id} onClick={() => void selectSpan(span)}><span className={`trace-span-icon ${span.type.toLowerCase()}`} aria-hidden="true">{span.type === "MODEL" ? <Bot size={14} /> : span.type === "CONTEXT_BUILD" ? <FileText size={14} /> : span.type === "TOOL" ? <SearchIcon size={14} /> : <GitBranch size={14} />}</span><span className="trace-span-copy"><strong>{span.name}</strong><small>{span.type} · {span.duration_ms ?? "—"} ms · {tokenLabel(span.usage.total_tokens)} tokens</small></span><StatusBadge status={span.status} /></button>)}
          </div>
          <div className="trace-detail">{selected ? <><div className="trace-detail-heading"><div><span className="panel-kicker">Span detail</span><h3>{selected.name}</h3></div><StatusBadge status={selected.status} /></div><div className="trace-detail-meta"><span><small>Type</small><b>{selected.type}</b></span><span><small>Duration</small><b>{selected.duration_ms ?? "—"} ms</b></span><span><small>Started</small><b>{dateLabel(selected.started_at)}</b></span></div><section className="trace-usage-panel" aria-label="Token usage"><div className="trace-usage-heading"><h4>Token usage</h4>{selected.usage.input_tokens_estimated ? <span>Input estimated</span> : null}</div><div className="trace-usage-grid"><span><small>Input</small><b>{tokenLabel(selected.usage.input_tokens)}</b></span><span><small>Output</small><b>{tokenLabel(selected.usage.output_tokens)}</b></span><span><small>Total</small><b>{tokenLabel(selected.usage.total_tokens)}</b></span><span><small>Cached input</small><b>{tokenLabel(selected.usage.cached_input_tokens)}</b></span></div></section><h4>Attributes</h4><pre>{JSON.stringify(selected.attributes, null, 2)}</pre>{selected.input ? <><h4>Input</h4><pre>{JSON.stringify(selected.input, null, 2)}</pre></> : null}{selected.output ? <><h4>Output</h4><pre>{JSON.stringify(selected.output, null, 2)}</pre></> : null}{selected.error ? <><h4>Error</h4><pre>{JSON.stringify(selected.error, null, 2)}</pre></> : null}</> : <div className="trace-empty">Select a span to inspect its payload.</div>}</div>
        </div>}
      </section>
    </div>,
    document.body,
  );
}

export default function PlaygroundPage() {
  const params = useParams<{ agentId: string }>();
  const router = useRouter();
  const agentId = params.agentId;
  const [agent, setAgent] = useState<Agent | null>(null);
  const [versions, setVersions] = useState<AgentVersionSummary[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [composer, setComposer] = useState("");
  const [lastRun, setLastRun] = useState<Run | null>(null);
  const [traceRunId, setTraceRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<"READY" | "RUNNING" | "COMPLETED" | "FAILED">("READY");
  const [streamingText, setStreamingText] = useState("");
  const [streamRunId, setStreamRunId] = useState<string | null>(null);
  const [toolActivity, setToolActivity] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const pendingDeltaRef = useRef("");
  const deltaFrameRef = useRef<number | null>(null);

  const flushDelta = useCallback(() => {
    if (!pendingDeltaRef.current) return;
    const pending = pendingDeltaRef.current;
    pendingDeltaRef.current = "";
    setStreamingText((current) => current + pending);
  }, []);

  const queueDelta = useCallback((delta: string) => {
    pendingDeltaRef.current += delta;
    if (deltaFrameRef.current !== null) return;
    deltaFrameRef.current = window.requestAnimationFrame(() => {
      deltaFrameRef.current = null;
      flushDelta();
    });
  }, [flushDelta]);

  useEffect(() => () => {
    abortControllerRef.current?.abort();
    if (deltaFrameRef.current !== null) window.cancelAnimationFrame(deltaFrameRef.current);
  }, []);

  const reloadMessages = useCallback(async (id: string): Promise<Message[]> => {
    const history = await fetchMessages(id);
    setMessages(history);
    return history;
  }, []);

  const restoreLatestRun = useCallback(async (history: Message[]) => {
    const latestRunId = [...history].reverse().find((message) => message.run_id)?.run_id;
    if (!latestRunId) {
      setLastRun(null);
      setStatus("READY");
      return;
    }

    try {
      const run = await fetchRun(latestRunId);
      setLastRun(run);
      setStatus(run.status === "COMPLETED" ? "COMPLETED" : run.status === "FAILED" ? "FAILED" : "RUNNING");
    } catch {
      // Keep the conversation usable if an old run is no longer available.
      setLastRun(null);
      setStatus("READY");
    }
  }, []);

  useEffect(() => {
    const element = messageListRef.current;
    if (!element) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    element.scrollTo({ top: element.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
  }, [messages.length, busy, streamingText]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [agentData, versionData, sessionData] = await Promise.all([fetchAgent(agentId), fetchVersions(agentId), fetchSessions(agentId)]);
        if (cancelled) return;
        setAgent(agentData); setVersions(versionData); setSelectedVersionId(versionData[0]?.id ?? ""); setSessions(sessionData);
        const querySession = new URLSearchParams(window.location.search).get("session_id");
        const selected = sessionData.find((item) => item.id === querySession) ?? (querySession ? null : sessionData[0]) ?? null;
        if (selected) {
          setSessionId(selected.id);
          const history = await reloadMessages(selected.id);
          if (!cancelled) await restoreLatestRun(history);
        }
      } catch (reason: unknown) { if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load playground."); }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [agentId, reloadMessages, restoreLatestRun]);

  const selectedVersion = useMemo(() => versions.find((version) => version.id === selectedVersionId) ?? null, [versions, selectedVersionId]);
  const conversationItems = useMemo(() => groupConversation(messages), [messages]);

  async function newSession() {
    setError(null);
    try {
      const created = await createSession(agentId);
      setSessions((items) => [created, ...items]); setSessionId(created.id); setMessages([]); setLastRun(null); setStatus("READY"); setStreamingText(""); setStreamRunId(null);
      router.replace(`/agents/${agentId}/playground?session_id=${created.id}`);
    } catch (reason: unknown) { setError(reason instanceof Error ? reason.message : "Unable to create session."); }
  }

  async function sendMessage() {
    const text = composer.trim();
    if (!text || !sessionId || !selectedVersionId || busy) return;
    const optimisticMessage: Message = {
      id: `optimistic-${crypto.randomUUID()}`,
      session_id: sessionId,
      run_id: null,
      role: "USER",
      sequence_no: messages.length + 1,
      content: { type: "text", text },
      token_count: null,
      created_at: new Date().toISOString(),
    };
    setMessages((items) => [...items, optimisticMessage]);
    setBusy(true); setStatus("RUNNING"); setError(null); setLastRun(null); setComposer(""); setStreamingText(""); setStreamRunId(null); setToolActivity(null); pendingDeltaRef.current = "";
    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      let activeRunId: string | null = null;
      let terminal: "COMPLETED" | "FAILED" | null = null;
      let failureMessage: string | null = null;
      for await (const event of createRunStream(agentId, sessionId, selectedVersionId, text, controller.signal)) {
        if (event.event === "run.started") {
          activeRunId = event.data.run_id;
          setStreamRunId(activeRunId);
          setStatus("RUNNING");
        } else if (event.event === "message.delta") {
          queueDelta(event.data.delta);
        } else if (event.event === "tool.started") {
          setToolActivity("Searching web…");
        } else if (event.event === "tool.completed" || event.event === "tool.failed") {
          setToolActivity(null);
        } else if (event.event === "run.completed") {
          terminal = "COMPLETED";
        } else if (event.event === "run.failed") {
          terminal = "FAILED";
          failureMessage = event.data.error.message;
        }
      }
      flushDelta();
      let resolvedStatus: "COMPLETED" | "FAILED" | null = terminal;
      if (activeRunId) {
        const run = await fetchRun(activeRunId);
        setLastRun(run);
        resolvedStatus = run.status === "COMPLETED" ? "COMPLETED" : run.status === "FAILED" ? "FAILED" : terminal;
        setStatus(resolvedStatus ?? "RUNNING");
        failureMessage = failureMessage ?? run.error?.message ?? null;
      }
      await reloadMessages(sessionId);
      // Keep any partial assistant text visible when the provider fails after
      // emitting deltas. A failed run should explain what happened without
      // making the user's response disappear behind tool activity.
      if (resolvedStatus === "COMPLETED") setStreamingText("");
      setToolActivity(null);
      if (resolvedStatus === "FAILED") setError(failureMessage ?? "The run failed. Try again.");
    } catch (reason: unknown) {
      setStatus("FAILED");
      try {
        await reloadMessages(sessionId);
      } catch {
        // Keep the optimistic query visible if the history refresh also fails.
      }
      if (reason instanceof RuntimeApiError && reason.runId) {
        try {
          setLastRun(await fetchRun(reason.runId));
        } catch {
          setLastRun({ id: reason.runId, trace_id: reason.traceId ?? "", status: "FAILED" } as Run);
        }
      }
      setError(reason instanceof Error ? reason.message : "The run failed. Try again.");
    } finally { abortControllerRef.current = null; setBusy(false); }
  }

  if (loading) return <AppShell><section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading playground…</section></AppShell>;
  if (!agent) return <AppShell><section className="panel agent-empty-state"><CircleAlert size={28} aria-hidden="true" /><h2>Playground unavailable</h2><p className="panel-copy">{error || "This agent could not be found."}</p><button className="button secondary-button" type="button" onClick={() => router.push("/agents")}>Back to agents</button></section></AppShell>;

  return <AppShell><div className="playground-page">
    <header className="page-header playground-header"><div><button className="text-button" type="button" onClick={() => router.push(`/agents/${agentId}`)}><ArrowLeft size={14} aria-hidden="true" />Back to agent</button><p className="eyebrow agent-eyebrow">VibesFactory / Runtime</p><div className="playground-title"><span className="agent-avatar large"><Bot size={19} aria-hidden="true" /></span><div><h1>{agent.name} playground</h1><p className="page-description">Run a published immutable version against a persisted session.</p></div></div></div><div className="header-controls playground-controls"><label className="playground-version-select"><span>Agent version</span><select aria-label="Agent version" value={selectedVersionId} onChange={(event) => setSelectedVersionId(event.target.value)} disabled={busy || versions.length === 0}><option value="" disabled>Select published version</option>{versions.map((version) => <option value={version.id} key={version.id}>v{version.version_number}{version.change_note ? ` · ${version.change_note}` : ""}</option>)}</select><ChevronDown size={15} aria-hidden="true" /></label><button className="button secondary-button" type="button" onClick={() => void newSession()} disabled={busy}><Plus size={15} aria-hidden="true" />New session</button></div></header>
    {error ? <div className="form-error playground-alert" role="alert"><CircleAlert size={15} aria-hidden="true" />{error}{lastRun?.id && lastRun.trace_id ? <button className="text-button" type="button" onClick={() => setTraceRunId(lastRun.id)}>Open failed trace</button> : null}</div> : null}
    {!selectedVersion ? <section className="panel agent-empty-state playground-empty"><GitBranch size={28} aria-hidden="true" /><h2>Publish a version to run this agent</h2><p className="panel-copy">The playground never executes mutable draft state. Publish an immutable version from the agent configuration first.</p><button className="button primary-button" type="button" onClick={() => router.push(`/agents/${agentId}`)}>Open agent configuration</button></section> : !sessionId ? <section className="panel agent-empty-state playground-empty"><Database size={28} aria-hidden="true" /><h2>Start a playground session</h2><p className="panel-copy">Create a session to persist this conversation and its runtime traces.</p><button className="button primary-button" type="button" onClick={() => void newSession()}><Plus size={15} aria-hidden="true" />New session</button></section> : <main className="playground-layout">
      <section className="panel playground-chat-panel" aria-busy={busy}><div className="playground-panel-heading"><div><span className="panel-kicker">Conversation</span><h2>{sessions.find((item) => item.id === sessionId)?.title || "Playground session"}</h2><p><code>{sessionId.slice(0, 8)}…</code> · {messages.length} messages</p></div><div className="run-status-area"><StatusBadge status={status} /><span className="sr-only" role="status" aria-live="polite" aria-atomic="true">{busy ? (toolActivity ?? (streamingText ? "Generating response" : "Starting run")) : status === "COMPLETED" ? "Response complete" : status === "FAILED" ? "Response failed" : "Ready"}</span>{lastRun?.usage?.total_tokens ? <span className="token-summary">{lastRun.usage.total_tokens.toLocaleString()} tokens</span> : null}</div></div><div className="message-list" ref={messageListRef} aria-label="Conversation messages">{messages.length === 0 && !busy ? <div className="message-empty"><Bot size={25} aria-hidden="true" /><strong>Ready when you are</strong><span>Send a prompt to test version {selectedVersion.version_number}.</span></div> : conversationItems.map((item, index) => item.kind === "message" ? <PlaygroundMessage key={item.message.id} message={item.message} agentName={agent.name} tools={item.tools} /> : <ToolActivityGroup key={"orphan-tools-" + index} tools={item.tools} />)}{toolActivity ? <div className="tool-runtime-panel tool-runtime-live" role="status"><LoaderCircle className="spin" size={14} aria-hidden="true" />{toolActivity}</div> : null}{streamingText ? <article className="playground-message assistant streaming-message" aria-label="Streaming assistant response"><div className="message-meta"><span>{agent.name}</span><span>Now</span></div><MessageContent message={{ id: `streaming-${streamRunId ?? "pending"}`, session_id: sessionId, run_id: streamRunId, role: "ASSISTANT", sequence_no: messages.length + 1, content: { type: "text", text: streamingText }, token_count: null, created_at: new Date().toISOString() }} /></article> : null}{busy && !streamingText && !toolActivity ? <article className="playground-message assistant processing-message"><div className="message-meta"><span>{agent.name}</span><span>Now</span></div><div className="processing-indicator"><LoaderCircle className="spin" size={15} aria-hidden="true" /><span>Agent is processing…</span></div></article> : null}</div><div className="composer-wrap"><label htmlFor="playground-composer">Message</label><div className="composer-row"><textarea id="playground-composer" value={composer} onChange={(event) => setComposer(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} placeholder="Ask your agent something…" rows={3} disabled={busy} /><button className="button primary-button send-button" type="button" onClick={() => void sendMessage()} disabled={busy || !composer.trim()} aria-label={busy ? "Sending message" : "Send message"}>{busy ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}</button></div><span className="field-helper">Enter to send · Shift + Enter for a new line</span></div></section>
      <aside className="playground-side-column"><section className="panel runtime-summary-panel"><div className="panel-heading"><div><span className="panel-kicker">Runtime context</span><h2>Execution summary</h2></div><Clock3 size={17} aria-hidden="true" /></div><dl className="runtime-summary-list"><div><dt>Version</dt><dd>v{selectedVersion.version_number}</dd></div><div><dt>Version ID</dt><dd>{selectedVersion.id.slice(0, 8)}…</dd></div><div><dt>Session</dt><dd>{sessionId.slice(0, 8)}…</dd></div><div><dt>Usage</dt><dd>{lastRun?.usage?.total_tokens?.toLocaleString() ?? "—"} tokens</dd></div><div><dt>Estimated cost</dt><dd>{lastRun?.estimated_cost ?? "—"}</dd></div></dl><div className="runtime-note"><Check size={14} aria-hidden="true" />Version pinned for reproducible runs.</div></section><section className="panel recent-run-panel"><div className="panel-heading"><div><span className="panel-kicker">Observability</span><h2>Latest run</h2></div></div>{lastRun ? <><div className="latest-run-row"><StatusBadge status={lastRun.status} /><code>{lastRun.id.slice(0, 12)}…</code></div>{lastRun.trace_id ? <button className="button secondary-button full-button" type="button" onClick={() => setTraceRunId(lastRun.id)}><GitBranch size={15} aria-hidden="true" />Inspect trace</button> : null}</> : <p className="panel-copy">Your first run will appear here with its trace and usage.</p>}</section></aside>
    </main>}
    {traceRunId ? <TraceInspector runId={traceRunId} onClose={() => setTraceRunId(null)} /> : null}
  </div></AppShell>;
}
