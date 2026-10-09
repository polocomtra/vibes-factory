"use client";

import { ArrowLeft, Ban, Bot, Copy, LoaderCircle, MessageSquare, Plus, Send } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";

import { AppShell } from "../../../../components/app-shell";
import { WorkflowRunView } from "../../../../components/workflow-run-view";
import { PrimaryTextArea } from "../../../../components/primary-text-field";
import { cancelWorkflowRun, createWorkflowChat, createWorkflowChatTurn, fetchWorkflow, fetchWorkflowChat, fetchWorkflowChatMessages, fetchWorkflowChatTurn, fetchWorkflowChats, fetchWorkflowRun, fetchWorkflowVersion, fetchWorkflowVersions, type Workflow, type WorkflowChatMessage, type WorkflowChatSession, type WorkflowNodeRun, type WorkflowRun, type WorkflowVersion } from "../../../../lib/workflows";

const ACCENTS: Record<string, string> = { START: "var(--success)", END: "var(--text-tertiary)", AGENT: "var(--brand-primary)", TOOL: "var(--info)", CONDITION: "var(--warning)", TRANSFORM: "var(--focus-ring)", APPROVAL: "var(--brand-primary)" };

async function fetchAllChatMessages(chatId: string) {
  const messages: WorkflowChatMessage[] = [];
  let after = 0;
  let hasMore = true;
  while (hasMore && messages.length < 2_000) {
    const page = await fetchWorkflowChatMessages(chatId, after);
    messages.push(...page.data);
    hasMore = page.pagination.has_more;
    if (page.pagination.next_cursor !== null) after = page.pagination.next_cursor;
    else hasMore = false;
  }
  return messages;
}

export default function WorkflowChatPage() {
  const params = useParams<{ workflowId: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [versions, setVersions] = useState<Array<{ id: string; version_number: number; configuration?: Record<string, unknown> }>>([]);
  const [chats, setChats] = useState<WorkflowChatSession[]>([]);
  const [chat, setChat] = useState<WorkflowChatSession | null>(null);
  const [version, setVersion] = useState<WorkflowVersion | null>(null);
  const [messages, setMessages] = useState<WorkflowChatMessage[]>([]);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [runs, setRuns] = useState<Record<string, WorkflowRun>>({});
  const [draft, setDraft] = useState("");
  const [retryMessage, setRetryMessage] = useState<string | null>(null);
  const [turnId, setTurnId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [nodeRuns, setNodeRuns] = useState<WorkflowNodeRun[]>([]);
  const [mobileTab, setMobileTab] = useState<"chat" | "execution">("chat");
  const messagesRef = useRef<HTMLDivElement>(null);
  const lastSubmittedRef = useRef("");
  const forceFollowRef = useRef(false);
  const [following, setFollowing] = useState(true);
  const [newMessages, setNewMessages] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [copiedRunId, setCopiedRunId] = useState<string | null>(null);

  const chatId = search.get("chatId");
  const eligibleVersions = useMemo(() => versions.filter((item) => (item.configuration?.chat as Record<string, unknown> | undefined)?.enabled === true), [versions]);
  const latestEligible = eligibleVersions[0] ?? null;

  const refreshMessages = useCallback(async (id: string) => {
    const nextMessages = await fetchAllChatMessages(id);
    setMessages(nextMessages);
    const ids = [...new Set(nextMessages.flatMap((message) => message.workflow_run_id ? [message.workflow_run_id] : []))];
    const loaded = await Promise.all(ids.map((runId) => fetchWorkflowRun(runId).catch(() => null)));
    setRuns(Object.fromEntries(loaded.filter((item): item is WorkflowRun => item !== null).map((item) => [item.id, item])));
  }, []);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true); setError(null);
      try {
        const [loadedWorkflow, loadedVersions, loadedChats] = await Promise.all([fetchWorkflow(params.workflowId), fetchWorkflowVersions(params.workflowId), fetchWorkflowChats(params.workflowId)]);
        if (!active) return;
        setWorkflow(loadedWorkflow); setVersions(loadedVersions); setChats(loadedChats);
        if (chatId) {
          const [loadedChat, loadedMessages] = await Promise.all([fetchWorkflowChat(chatId), fetchAllChatMessages(chatId)]);
          if (!active) return;
          if (loadedChat.workflow_id !== params.workflowId) throw new Error("This conversation belongs to a different workflow.");
          const loadedVersion = await fetchWorkflowVersion(loadedChat.workflow_version_id);
          if (!active) return;
          setChat(loadedChat); setMessages(loadedMessages); setVersion(loadedVersion);
          const runIds = [...new Set([...loadedMessages.flatMap((item) => item.workflow_run_id ? [item.workflow_run_id] : []), ...(loadedChat.active_run_id ? [loadedChat.active_run_id] : [])])];
          const loadedRuns = await Promise.all(runIds.map((id) => fetchWorkflowRun(id).catch(() => null)));
          if (!active) return;
          const map = Object.fromEntries(loadedRuns.filter((item): item is WorkflowRun => item !== null).map((item) => [item.id, item]));
          setRuns(map); setRun(loadedChat.active_run_id ? map[loadedChat.active_run_id] ?? null : null);
        } else {
          setChat(null); setMessages([]); setVersion(null); setRun(null);
        }
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : "Unable to load workflow chat."); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [params.workflowId, chatId]);

  useEffect(() => {
    if (!turnId) return;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const turn = await fetchWorkflowChatTurn(turnId);
        if (!active) return;
        if (turn.status === "COMPLETED" || turn.status === "FAILED") {
          setTurnId(null); setBusy(false);
          if (turn.status === "FAILED") {
            setError(`${turn.error?.message ?? "The chat request failed."}${turn.error?.code ? ` (${turn.error.code})` : ""}`);
            setRetryMessage(lastSubmittedRef.current || null);
          } else setRetryMessage(null);
          if (chat) {
            await refreshMessages(chat.id);
            const updated = await fetchWorkflowChat(chat.id);
            setChat(updated);
            if (updated.active_run_id) setRun(await fetchWorkflowRun(updated.active_run_id));
          }
        }
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : "Unable to check the chat response."); }
    }, 900);
    return () => { active = false; window.clearInterval(timer); };
  }, [turnId, chat, refreshMessages]);

  useEffect(() => {
    if (!chat?.active_run_id) { setRun(null); return; }
    let active = true;
    const timer = window.setInterval(() => { void fetchWorkflowRun(chat.active_run_id!).then((next) => { if (active) { setRun(next); setRuns((current) => ({ ...current, [next.id]: next })); } }).catch(() => undefined); }, 1800);
    void fetchWorkflowRun(chat.active_run_id).then((next) => { if (active) { setRun(next); setRuns((current) => ({ ...current, [next.id]: next })); } }).catch(() => undefined);
    return () => { active = false; window.clearInterval(timer); };
  }, [chat?.active_run_id]);

  async function newChat() {
    if (!latestEligible) return;
    setBusy(true); setError(null);
    setFollowing(true); setNewMessages(false); forceFollowRef.current = true;
    try {
      const created = await createWorkflowChat(params.workflowId, latestEligible.id);
      setChats((current) => [created, ...current]);
      router.replace(`/workflows/${params.workflowId}/chat?chatId=${created.id}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start a workflow chat."); }
    finally { setBusy(false); }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!chat || !draft.trim() || busy) return;
    setBusy(true); setError(null);
    setFollowing(true); setNewMessages(false); forceFollowRef.current = true;
    const submitted = draft.trim();
    lastSubmittedRef.current = submitted;
    try {
      const turn = await createWorkflowChatTurn(chat.id, submitted, crypto.randomUUID());
      setMessages((current) => [...current, { id: `pending-${turn.id}`, sequence_no: Math.max(0, ...current.map((message) => message.sequence_no)) + 1, role: "USER", kind: "TEXT", content: { text: submitted }, workflow_run_id: null, created_at: new Date().toISOString() }]);
      setDraft(""); setTurnId(turn.id); setRetryMessage(null); setMobileTab("chat");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to send this message."); setRetryMessage(submitted); setBusy(false); }
  }

  async function retryLastMessage() {
    if (!chat || !retryMessage || busy) return;
    setBusy(true); setError(null);
    try {
      const turn = await createWorkflowChatTurn(chat.id, retryMessage, crypto.randomUUID());
      setTurnId(turn.id); lastSubmittedRef.current = retryMessage; setRetryMessage(null); setFollowing(true); forceFollowRef.current = true; setDraft(""); setMobileTab("chat");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to retry this message.");
      setBusy(false);
    }
  }

  async function cancelRun() {
    if (!run || cancelling) return;
    setCancelling(true);
    try { const cancelled = await cancelWorkflowRun(run.id); setRun(cancelled); setRuns((current) => ({ ...current, [cancelled.id]: cancelled })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to cancel this workflow run."); }
    finally { setCancelling(false); }
  }

  const graph = useMemo(() => {
    if (!version) return { nodes: [] as Node[], edges: [] as Edge[] };
    const nodeStatus = new Map<string, string>();
    nodeRuns.forEach((item) => nodeStatus.set(item.node_key, item.status));
    if (run?.current_node_key && !nodeStatus.has(run.current_node_key)) nodeStatus.set(run.current_node_key, "RUNNING");
    return {
      nodes: version.definition.nodes.map((item, index) => ({ id: item.key, position: item.position ?? { x: 70 + index * 220, y: 80 }, data: { label: `${item.name} · ${nodeStatus.get(item.key) ?? "PENDING"}`, kind: item.type, status: nodeStatus.get(item.key) ?? "PENDING" }, style: { borderColor: selectedNode === item.key ? "var(--focus-ring)" : nodeStatus.get(item.key) ? ACCENTS[item.type] : "var(--border-default)", background: "var(--surface-primary)", color: "var(--text-primary)", borderRadius: 10, borderWidth: selectedNode === item.key ? 2 : 1, padding: "10px 14px", minWidth: 150 } })),
      edges: version.definition.edges.map((item, index) => ({ id: `chat-edge-${index}`, source: item.source, target: item.target, label: item.source_handle ?? undefined, type: "smoothstep" as const, animated: item.source === run?.current_node_key })),
    };
  }, [version, run, nodeRuns, selectedNode]);

  const activeRunId = chat?.active_run_id;

  useEffect(() => {
    if (!following) { setNewMessages(true); return; }
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const container = messagesRef.current;
    forceFollowRef.current = true;
    container?.scrollTo({ top: container.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
    window.setTimeout(() => { forceFollowRef.current = false; }, 450);
    setNewMessages(false);
  }, [messages, busy, run?.status, following]);

  return <AppShell><div className="workflow-chat-page">
    <Link className="back-link" href={`/workflows/${params.workflowId}`}><ArrowLeft size={15} aria-hidden="true" />Back to workflow</Link>
    <header className="page-header workflow-chat-header"><div><p className="eyebrow">VibesFactory / Workflows / Chat</p><h1>{workflow?.name ?? "Workflow chat"}</h1><p className="page-description">Describe what you need. The assistant gathers inputs and follows the workflow as it runs.</p></div><div className="workflow-chat-header-actions">{version ? <span className="status-badge muted">Version {version.version_number}</span> : null}<button className="button primary-button" type="button" onClick={() => void newChat()} disabled={busy || !latestEligible}><Plus size={15} aria-hidden="true" />New chat</button></div></header>
    <div className="workflow-chat-mobile-tabs" role="tablist" aria-label="Workflow chat panels"><button type="button" role="tab" aria-selected={mobileTab === "chat"} onClick={() => setMobileTab("chat")}>Chat</button><button type="button" role="tab" aria-selected={mobileTab === "execution"} onClick={() => setMobileTab("execution")}>Execution</button>{run ? <span role="status">{run.status}{run.current_node_name ? ` · ${run.current_node_name}` : ""}</span> : null}</div>
    {error ? <div className="form-error agent-alert" role="alert"><span>{error}</span>{retryMessage && chat ? <button className="button subtle-button" type="button" onClick={() => void retryLastMessage()} disabled={busy}>Retry last message</button> : null}</div> : null}
    {loading ? <section className="panel agent-state"><LoaderCircle className="spin" size={18} />Loading workflow chat…</section> : !latestEligible && !chat ? <section className="panel workflow-chat-empty"><MessageSquare size={22} /><h2>Chat is not enabled for this workflow</h2><p>Define workflow inputs, enable the chat assistant, then publish a new version.</p><Link className="button secondary-button" href={`/workflows/${params.workflowId}`}>Open workflow editor</Link></section> : !chat ? <section className="panel workflow-chat-empty"><Bot size={22} /><h2>Start a workflow conversation</h2><p>{chats.length ? "Choose a recent conversation or start a new one." : "Tell the assistant what you want this workflow to do."}</p><button className="button primary-button" type="button" onClick={() => void newChat()} disabled={busy}><Plus size={15} aria-hidden="true" />New chat</button>{chats.length ? <div className="workflow-chat-history"><span className="panel-label">Recent conversations</span>{chats.map((item) => <Link key={item.id} href={`/workflows/${params.workflowId}/chat?chatId=${item.id}`}>{item.title || "Workflow conversation"}<small>{new Date(item.updated_at).toLocaleString()}</small></Link>)}</div> : null}</section> : <div className="workflow-chat-layout">
      <section className={`panel workflow-chat-conversation ${mobileTab === "execution" ? "mobile-hidden" : ""}`} aria-label="Workflow conversation">
        <div className="workflow-chat-conversation-header"><div><span className="panel-label">Conversation</span><strong>{chat.title || "New conversation"}</strong></div><details className="workflow-chat-history-menu"><summary>History</summary><nav aria-label="Recent workflow conversations">{chats.map((item) => <Link key={item.id} href={`/workflows/${params.workflowId}/chat?chatId=${item.id}`} aria-current={item.id === chat.id ? "page" : undefined}>{item.title || "New conversation"}<small>{new Date(item.updated_at).toLocaleString()}</small></Link>)}</nav></details></div>
        <div className="workflow-chat-messages" aria-label="Messages" ref={messagesRef} onScroll={(event) => { const element = event.currentTarget; const atBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 48; if (atBottom) { forceFollowRef.current = false; setFollowing(true); setNewMessages(false); } else if (!forceFollowRef.current) { setFollowing(false); setNewMessages(true); } }}>
          {messages.length === 0 ? <div className="workflow-chat-welcome"><Bot size={23} aria-hidden="true" /><strong>What would you like to do?</strong><p>{String(((version?.configuration.chat as Record<string, unknown> | undefined)?.description) ?? "Describe the outcome you want, and I’ll gather any workflow inputs I need.")}</p></div> : messages.map((message) => <article key={message.id} className={`workflow-chat-message ${message.role.toLowerCase()}`}>
            <span className="workflow-chat-message-role">{message.role === "USER" ? "You" : "Workflow assistant"}</span>
            {message.kind === "WORKFLOW_RUN" ? (() => { const cardRun = message.workflow_run_id ? runs[message.workflow_run_id] : run; const outputText = cardRun?.output ? String(cardRun.output.markdown ?? cardRun.output.text ?? cardRun.output.content ?? JSON.stringify(cardRun.output, null, 2)) : ""; return <div className="workflow-chat-run-card"><div><span>Workflow run</span><strong>{cardRun?.status ?? "QUEUED"}</strong></div><details className="workflow-chat-input-summary"><summary>Inputs used</summary><pre><code>{JSON.stringify(message.content.input ?? {}, null, 2)}</code></pre></details>{cardRun?.output ? <><div className="workflow-chat-run-links"><button className="button secondary-button" type="button" onClick={() => { void navigator.clipboard.writeText(outputText).then(() => { setCopiedRunId(cardRun.id); window.setTimeout(() => setCopiedRunId(null), 1600); }); }}><Copy size={14} aria-hidden="true" />{copiedRunId === cardRun.id ? "Copied" : "Copy output"}</button><Link href={`/traces/${cardRun.trace_id}`}>Open trace</Link></div><article className="workflow-output-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{outputText}</ReactMarkdown></article></> : cardRun?.error ? <p role="alert">{cardRun.error.message}</p> : <p>The final response will appear here when execution completes.</p>}{cardRun ? <Link href={`/workflow-runs/${cardRun.id}`}>Open run details</Link> : null}</div>; })() : <div className="workflow-chat-message-body"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{String(message.content.text ?? "")}</ReactMarkdown></div>}
          </article>)}
          {busy ? <p className="workflow-chat-thinking" role="status"><LoaderCircle size={15} className="spin" />Gathering workflow context…</p> : null}
          <div aria-live="polite" aria-atomic="true" className="sr-only">{run ? `Workflow status: ${run.status}${run.current_node_name ? `, ${run.current_node_name}` : ""}` : ""}</div>
        </div>
        {newMessages ? <button className="workflow-chat-jump-latest" type="button" onClick={() => { setFollowing(true); setNewMessages(false); }}>New activity · scroll to latest</button> : null}
        <form className="workflow-chat-composer" onSubmit={(event) => void sendMessage(event)}><label htmlFor="workflow-chat-message">Message the workflow assistant</label><PrimaryTextArea id="workflow-chat-message" rows={3} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Describe what you want the workflow to do…" disabled={busy} /><div><small>Ask a question or describe a workflow run.</small><button className="button primary-button" type="submit" disabled={busy || !draft.trim()}><Send size={15} aria-hidden="true" />Send</button></div></form>
      </section>
      <section className={`workflow-chat-execution ${mobileTab === "chat" ? "mobile-hidden" : ""}`} aria-label="Workflow execution">
        <div className="panel workflow-chat-graph"><div className="panel-heading"><div><span className="eyebrow">Execution graph</span><h2>{run ? run.status : "Ready"}</h2></div><div className="workflow-chat-graph-actions">{run?.current_node_name ? <span className="status-badge muted">{run.current_node_name}</span> : null}{run && ["QUEUED", "RUNNING", "WAITING_APPROVAL"].includes(run.status) ? <button className="button subtle-button" type="button" onClick={() => void cancelRun()} disabled={cancelling}><Ban size={14} aria-hidden="true" />{cancelling ? "Cancelling…" : "Cancel run"}</button> : null}</div></div>{version ? <div className="workflow-chat-flow"><ReactFlow nodes={graph.nodes} edges={graph.edges} nodesDraggable={false} nodesConnectable={false} elementsSelectable onNodeClick={(_, node) => setSelectedNode(node.id)} onInit={(instance) => requestAnimationFrame(() => instance.fitView({ padding: 0.2 }))} fitView minZoom={0.2} maxZoom={1.4} proOptions={{ hideAttribution: true }}><Background gap={20} size={1} color="var(--grid-line)" /><Controls showInteractive={false} /></ReactFlow></div> : <p className="panel-copy">Load a conversation to view its published graph.</p>}
          <details className="workflow-chat-node-list"><summary>Keyboard accessible workflow nodes</summary><ul>{version?.definition.nodes.map((node) => <li key={node.key}><button type="button" aria-pressed={selectedNode === node.key} onClick={() => setSelectedNode(node.key)}><span style={{ background: ACCENTS[node.type] }} />{node.name}<code>{node.type}</code></button></li>)}</ul></details>
        </div>
        {activeRunId ? <div className="workflow-chat-run-observer"><WorkflowRunView runId={activeRunId} onSelectNode={setSelectedNode} onNodeRunsChange={setNodeRuns} selectedNodeKey={selectedNode} onClearNodeFilter={() => setSelectedNode(null)} /></div> : <section className="panel workflow-chat-execution-empty"><MessageSquare size={18} /><p>Run a workflow from chat to see its live timeline and agent activity here.</p></section>}
      </section>
    </div>}
  </div></AppShell>;
}
