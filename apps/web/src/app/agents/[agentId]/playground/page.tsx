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
  Send,
  X,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import ReactMarkdown, { type Components } from "react-markdown";
import { Children, isValidElement, type ReactElement, useCallback, useEffect, useMemo, useRef, useState } from "react";
import remarkGfm from "remark-gfm";

import { AppShell } from "../../../../components/app-shell";
import {
  createRun,
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

function PlaygroundMessage({ message, agentName }: { message: Message; agentName: string }) {
  const content = textOf(message);
  return <article className={`playground-message ${message.role.toLowerCase()}`}><div className="message-meta"><span>{message.role === "USER" ? "You" : message.role === "ASSISTANT" ? agentName : message.role}</span><div className="message-meta-actions"><time dateTime={message.created_at}>{dateLabel(message.created_at)}</time><CopyButton text={content} /></div></div><MessageContent message={message} /></article>;
}

function TraceInspector({ runId, onClose }: { runId: string; onClose: () => void }) {
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [spans, setSpans] = useState<Span[]>([]);
  const [selected, setSelected] = useState<Span | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return <div className="trace-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="trace-inspector" role="dialog" aria-modal="true" aria-labelledby="trace-title">
      <header className="trace-inspector-header"><div><span className="panel-kicker">Observability</span><h2 id="trace-title">Run trace</h2><p className="panel-copy">Inspect the persisted execution timeline for <code>{runId.slice(0, 8)}…</code>.</p></div><button className="icon-button" type="button" aria-label="Close trace inspector" onClick={onClose}><X size={17} aria-hidden="true" /></button></header>
      {error ? <div className="form-error" role="alert">{error}</div> : null}
      {!trace ? <div className="trace-loading"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading trace…</div> : <div className="trace-split-view">
        <div className="trace-timeline" aria-label="Trace spans">
          <div className="trace-summary"><StatusBadge status={trace.trace.status} /><span>{spans.length} spans</span></div>
          {spans.map((span) => <button className={selected?.id === span.id ? "trace-span selected" : "trace-span"} type="button" key={span.id} onClick={() => void selectSpan(span)}><span className={`trace-span-icon ${span.type.toLowerCase()}`} aria-hidden="true">{span.type === "MODEL" ? <Bot size={14} /> : span.type === "CONTEXT_BUILD" ? <FileText size={14} /> : <GitBranch size={14} />}</span><span className="trace-span-copy"><strong>{span.name}</strong><small>{span.type} · {span.duration_ms ?? "—"} ms · {tokenLabel(span.usage.total_tokens)} tokens</small></span><StatusBadge status={span.status} /></button>)}
        </div>
        <div className="trace-detail">{selected ? <><div className="trace-detail-heading"><div><span className="panel-kicker">Span detail</span><h3>{selected.name}</h3></div><StatusBadge status={selected.status} /></div><div className="trace-detail-meta"><span><small>Type</small><b>{selected.type}</b></span><span><small>Duration</small><b>{selected.duration_ms ?? "—"} ms</b></span><span><small>Started</small><b>{dateLabel(selected.started_at)}</b></span></div><section className="trace-usage-panel" aria-label="Token usage"><div className="trace-usage-heading"><h4>Token usage</h4>{selected.usage.input_tokens_estimated ? <span>Input estimated</span> : null}</div><div className="trace-usage-grid"><span><small>Input</small><b>{tokenLabel(selected.usage.input_tokens)}</b></span><span><small>Output</small><b>{tokenLabel(selected.usage.output_tokens)}</b></span><span><small>Total</small><b>{tokenLabel(selected.usage.total_tokens)}</b></span><span><small>Cached input</small><b>{tokenLabel(selected.usage.cached_input_tokens)}</b></span></div></section><h4>Attributes</h4><pre>{JSON.stringify(selected.attributes, null, 2)}</pre>{selected.input ? <><h4>Input</h4><pre>{JSON.stringify(selected.input, null, 2)}</pre></> : null}{selected.output ? <><h4>Output</h4><pre>{JSON.stringify(selected.output, null, 2)}</pre></> : null}{selected.error ? <><h4>Error</h4><pre>{JSON.stringify(selected.error, null, 2)}</pre></> : null}</> : <div className="trace-empty">Select a span to inspect its payload.</div>}</div>
      </div>}
    </section>
  </div>;
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
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messageListRef = useRef<HTMLDivElement>(null);

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
  }, [messages.length, busy]);

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

  async function newSession() {
    setError(null);
    try {
      const created = await createSession(agentId);
      setSessions((items) => [created, ...items]); setSessionId(created.id); setMessages([]); setLastRun(null); setStatus("READY");
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
    setBusy(true); setStatus("RUNNING"); setError(null); setLastRun(null); setComposer("");
    try {
      const run = await createRun(agentId, sessionId, selectedVersionId, text);
      setLastRun(run); setStatus(run.status === "COMPLETED" ? "COMPLETED" : "FAILED");
      await reloadMessages(sessionId);
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
    } finally { setBusy(false); }
  }

  if (loading) return <AppShell><section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading playground…</section></AppShell>;
  if (!agent) return <AppShell><section className="panel agent-empty-state"><CircleAlert size={28} aria-hidden="true" /><h2>Playground unavailable</h2><p className="panel-copy">{error || "This agent could not be found."}</p><button className="button secondary-button" type="button" onClick={() => router.push("/agents")}>Back to agents</button></section></AppShell>;

  return <AppShell><div className="playground-page">
    <header className="page-header playground-header"><div><button className="text-button" type="button" onClick={() => router.push(`/agents/${agentId}`)}><ArrowLeft size={14} aria-hidden="true" />Back to agent</button><p className="eyebrow agent-eyebrow">VibesFactory / Runtime</p><div className="playground-title"><span className="agent-avatar large"><Bot size={19} aria-hidden="true" /></span><div><h1>{agent.name} playground</h1><p className="page-description">Run a published immutable version against a persisted session.</p></div></div></div><div className="header-controls playground-controls"><label className="playground-version-select"><span>Agent version</span><select aria-label="Agent version" value={selectedVersionId} onChange={(event) => setSelectedVersionId(event.target.value)} disabled={busy || versions.length === 0}><option value="" disabled>Select published version</option>{versions.map((version) => <option value={version.id} key={version.id}>v{version.version_number}{version.change_note ? ` · ${version.change_note}` : ""}</option>)}</select><ChevronDown size={15} aria-hidden="true" /></label><button className="button secondary-button" type="button" onClick={() => void newSession()} disabled={busy}><Plus size={15} aria-hidden="true" />New session</button></div></header>
    {error ? <div className="form-error playground-alert" role="alert"><CircleAlert size={15} aria-hidden="true" />{error}{lastRun?.id && lastRun.trace_id ? <button className="text-button" type="button" onClick={() => setTraceRunId(lastRun.id)}>Open failed trace</button> : null}</div> : null}
    {!selectedVersion ? <section className="panel agent-empty-state playground-empty"><GitBranch size={28} aria-hidden="true" /><h2>Publish a version to run this agent</h2><p className="panel-copy">The playground never executes mutable draft state. Publish an immutable version from the agent configuration first.</p><button className="button primary-button" type="button" onClick={() => router.push(`/agents/${agentId}`)}>Open agent configuration</button></section> : !sessionId ? <section className="panel agent-empty-state playground-empty"><Database size={28} aria-hidden="true" /><h2>Start a playground session</h2><p className="panel-copy">Create a session to persist this conversation and its runtime traces.</p><button className="button primary-button" type="button" onClick={() => void newSession()}><Plus size={15} aria-hidden="true" />New session</button></section> : <main className="playground-layout">
      <section className="panel playground-chat-panel" aria-busy={busy}><div className="playground-panel-heading"><div><span className="panel-kicker">Conversation</span><h2>{sessions.find((item) => item.id === sessionId)?.title || "Playground session"}</h2><p><code>{sessionId.slice(0, 8)}…</code> · {messages.length} messages</p></div><div className="run-status-area" aria-live="polite"><StatusBadge status={status} />{lastRun?.usage?.total_tokens ? <span className="token-summary">{lastRun.usage.total_tokens.toLocaleString()} tokens</span> : null}</div></div><div className="message-list" ref={messageListRef} aria-label="Conversation messages">{messages.length === 0 && !busy ? <div className="message-empty"><Bot size={25} aria-hidden="true" /><strong>Ready when you are</strong><span>Send a prompt to test version {selectedVersion.version_number}.</span></div> : messages.map((message) => <PlaygroundMessage key={message.id} message={message} agentName={agent.name} />)}{busy ? <article className="playground-message assistant processing-message" aria-live="polite"><div className="message-meta"><span>{agent.name}</span><span>Now</span></div><div className="processing-indicator"><LoaderCircle className="spin" size={15} aria-hidden="true" /><span>Agent is processing…</span></div></article> : null}</div><div className="composer-wrap"><label htmlFor="playground-composer">Message</label><div className="composer-row"><textarea id="playground-composer" value={composer} onChange={(event) => setComposer(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} placeholder="Ask your agent something…" rows={3} disabled={busy} /><button className="button primary-button send-button" type="button" onClick={() => void sendMessage()} disabled={busy || !composer.trim()} aria-label={busy ? "Sending message" : "Send message"}>{busy ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}</button></div><span className="field-helper">Enter to send · Shift + Enter for a new line</span></div></section>
      <aside className="playground-side-column"><section className="panel runtime-summary-panel"><div className="panel-heading"><div><span className="panel-kicker">Runtime context</span><h2>Execution summary</h2></div><Clock3 size={17} aria-hidden="true" /></div><dl className="runtime-summary-list"><div><dt>Version</dt><dd>v{selectedVersion.version_number}</dd></div><div><dt>Version ID</dt><dd>{selectedVersion.id.slice(0, 8)}…</dd></div><div><dt>Session</dt><dd>{sessionId.slice(0, 8)}…</dd></div><div><dt>Usage</dt><dd>{lastRun?.usage?.total_tokens?.toLocaleString() ?? "—"} tokens</dd></div><div><dt>Estimated cost</dt><dd>{lastRun?.estimated_cost ?? "—"}</dd></div></dl><div className="runtime-note"><Check size={14} aria-hidden="true" />Version pinned for reproducible runs.</div></section><section className="panel recent-run-panel"><div className="panel-heading"><div><span className="panel-kicker">Observability</span><h2>Latest run</h2></div></div>{lastRun ? <><div className="latest-run-row"><StatusBadge status={lastRun.status} /><code>{lastRun.id.slice(0, 12)}…</code></div>{lastRun.trace_id ? <button className="button secondary-button full-button" type="button" onClick={() => setTraceRunId(lastRun.id)}><GitBranch size={15} aria-hidden="true" />Inspect trace</button> : null}</> : <p className="panel-copy">Your first run will appear here with its trace and usage.</p>}</section></aside>
    </main>}
    {traceRunId ? <TraceInspector runId={traceRunId} onClose={() => setTraceRunId(null)} /> : null}
  </div></AppShell>;
}
