"use client";

import { Bot, Check, CircleAlert, Clock3, LoaderCircle, Pencil, Plus, Search, Sparkles, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState, type FormEvent } from "react";

import { AppShell } from "../../components/app-shell";
import { type Agent, fetchAgents } from "../../lib/agents";
import { apiFetch, readApiError } from "../../lib/api";
import { createSession, fetchSessions, type Session, updateSession } from "../../lib/runtime";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };

function dateLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function AgentAvailability({ agent }: { agent: Agent }) {
  return agent.latest_version_number > 0
    ? <span className="status-badge success"><span aria-hidden="true" />v{agent.latest_version_number} ready</span>
    : <span className="status-badge muted"><span aria-hidden="true" />Draft only</span>;
}

function SessionItem({ session, selected, onSelect, onContinue, onRename }: { session: Session; selected: boolean; onSelect: () => void; onContinue: () => void; onRename: (title: string) => Promise<void> }) {
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(session.title ?? "");
  const [saving, setSaving] = useState(false);

  function cancelRename() {
    setDraft(session.title ?? "");
    setRenaming(false);
  }

  async function saveRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    try {
      await onRename(draft.trim());
      setRenaming(false);
    } catch {
      // The launcher displays the request error; keep the editor open for retry.
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={selected ? "playground-session-item selected" : "playground-session-item"} role="group" aria-label={`${session.title || "Untitled session"} ${session.id.slice(0, 8)}`}>
      {renaming ? (
        <form className="playground-session-rename-form" onSubmit={(event) => void saveRename(event)}>
          <label className="sr-only" htmlFor={`session-title-${session.id}`}>Session name</label>
          <input id={`session-title-${session.id}`} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") cancelRename(); }} maxLength={255} placeholder="Name this session" disabled={saving} />
          <button className="icon-button session-rename-action" type="submit" disabled={saving} aria-label="Save session name" title="Save name">{saving ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <Check size={16} aria-hidden="true" />}</button>
          <button className="icon-button session-rename-action" type="button" onClick={cancelRename} disabled={saving} aria-label="Cancel rename" title="Cancel"><X size={16} aria-hidden="true" /></button>
        </form>
      ) : (
        <button className="playground-session-select" type="button" aria-pressed={selected} onClick={onSelect}>
          <span className="playground-session-icon"><Clock3 size={15} aria-hidden="true" /></span>
          <span className="playground-session-copy"><strong>{session.title || "Untitled session"}</strong><small>Last activity {dateLabel(session.last_activity_at)}</small><code>{session.id.slice(0, 8)}…</code></span>
        </button>
      )}
      {!renaming ? <button className="icon-button session-rename-action" type="button" onClick={() => { setDraft(session.title ?? ""); setRenaming(true); }} aria-label={`Rename ${session.title || "session"}`} title="Rename session"><Pencil size={15} aria-hidden="true" /></button> : null}
      <button className="button primary-button session-continue-button" type="button" onClick={onContinue}>Continue session</button>
    </div>
  );
}

function PlaygroundLauncherContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedAgent = useMemo(() => agents.find((agent) => agent.id === selectedAgentId) ?? null, [agents, selectedAgentId]);
  const filteredAgents = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    if (!normalized) return agents;
    return agents.filter((agent) => `${agent.name} ${agent.slug} ${agent.description ?? ""}`.toLowerCase().includes(normalized));
  }, [agents, search]);

  useEffect(() => {
    let cancelled = false;
    async function loadWorkspaceAndAgents() {
      try {
        const response = await apiFetch("/v1/workspaces");
        if (!response.ok) throw new Error(await readApiError(response));
        const body = await response.json() as { data: Workspace[] };
        const saved = window.localStorage.getItem("vf-workspace-id");
        const selected = body.data.find((item) => item.id === saved) ?? body.data[0] ?? null;
        if (cancelled) return;
        setWorkspace(selected);
        if (!selected) return;

        const items = await fetchAgents(selected.id);
        if (cancelled) return;
        setAgents(items);
        const queryAgentId = searchParams.get("agent_id");
        const nextAgent = items.find((agent) => agent.id === queryAgentId) ?? items[0] ?? null;
        setSelectedAgentId(nextAgent?.id ?? "");
      } catch (reason: unknown) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load playground.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadWorkspaceAndAgents();
    return () => { cancelled = true; };
  }, [searchParams]);

  useEffect(() => {
    if (!selectedAgentId) {
      setSessions([]);
      setSelectedSessionId("");
      return;
    }
    let cancelled = false;
    setSessionsLoading(true);
    setError(null);
    void fetchSessions(selectedAgentId)
      .then((items) => {
        if (cancelled) return;
        setSessions(items);
        const querySessionId = searchParams.get("session_id");
        setSelectedSessionId(items.find((session) => session.id === querySessionId)?.id ?? items[0]?.id ?? "");
      })
      .catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load sessions."); })
      .finally(() => { if (!cancelled) setSessionsLoading(false); });
    return () => { cancelled = true; };
  }, [searchParams, selectedAgentId]);

  function selectAgent(agentId: string) {
    setSelectedAgentId(agentId);
    setSelectedSessionId("");
    const params = new URLSearchParams();
    params.set("agent_id", agentId);
    router.replace(`/playground?${params.toString()}`);
  }

  async function startNewSession() {
    if (!selectedAgent || selectedAgent.latest_version_number === 0 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createSession(selectedAgent.id);
      router.push(`/agents/${selectedAgent.id}/playground?session_id=${created.id}`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to create session.");
    } finally {
      setBusy(false);
    }
  }

  async function renameSession(sessionId: string, title: string) {
    setError(null);
    try {
      const updated = await updateSession(sessionId, title);
      setSessions((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to rename session.");
      throw reason;
    }
  }

  if (loading) return <AppShell><section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading playground…</section></AppShell>;

  return (
    <AppShell>
      <div className="page-header playground-launcher-header">
        <div>
          <p className="eyebrow">VibesFactory / Runtime</p>
          <h1>Playground</h1>
          <p className="page-description">Choose an agent, resume a persisted session, or start a fresh conversation.</p>
        </div>
        <span className="playground-workspace-label"><span className="status-pulse" aria-hidden="true" />{workspace?.name ?? "No workspace"}</span>
      </div>

      {error ? <div className="form-error playground-alert" role="alert"><CircleAlert size={15} aria-hidden="true" />{error}</div> : null}

      {!workspace ? (
        <section className="panel agent-empty-state playground-empty"><Bot size={30} aria-hidden="true" /><h2>Create a workspace first</h2><p className="panel-copy">Agents and their sessions are isolated by workspace.</p><button className="button primary-button" type="button" onClick={() => router.push("/settings")}>Open settings</button></section>
      ) : agents.length === 0 ? (
        <section className="panel agent-empty-state playground-empty"><Sparkles size={30} aria-hidden="true" /><h2>No agents available</h2><p className="panel-copy">Create and publish an agent before opening a runtime session.</p><button className="button primary-button" type="button" onClick={() => router.push("/agents/new")}>Create agent</button></section>
      ) : (
        <main className="playground-launcher-layout">
          <section className="panel playground-picker-panel" aria-labelledby="agent-picker-title">
            <div className="panel-heading"><div><span className="panel-kicker">Step 01</span><h2 id="agent-picker-title">Choose an agent</h2><p className="panel-copy">Only published versions can be executed.</p></div><Bot size={18} aria-hidden="true" /></div>
            <label className="playground-search"><Search size={15} aria-hidden="true" /><span className="sr-only">Search agents</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by name or slug…" /></label>
            <div className="playground-agent-list" role="listbox" aria-label="Agents">
              {filteredAgents.length === 0 ? <p className="playground-list-empty">No agents match your search.</p> : filteredAgents.map((agent) => <button className={agent.id === selectedAgentId ? "playground-agent-option selected" : "playground-agent-option"} type="button" role="option" aria-selected={agent.id === selectedAgentId} key={agent.id} onClick={() => selectAgent(agent.id)}><span className="agent-avatar"><Bot size={16} aria-hidden="true" /></span><span className="playground-agent-copy"><strong>{agent.name}</strong><small>{agent.description || agent.slug}</small></span><AgentAvailability agent={agent} /></button>)}
            </div>
          </section>

          <section className="panel playground-picker-panel session-picker-panel" aria-labelledby="session-picker-title">
            <div className="panel-heading"><div><span className="panel-kicker">Step 02</span><h2 id="session-picker-title">Choose a session</h2><p className="panel-copy">{selectedAgent ? `Continue ${selectedAgent.name} with its saved context.` : "Select an agent to load its sessions."}</p></div>{selectedAgent && selectedAgent.latest_version_number > 0 ? <button className="button primary-button session-header-create-button" type="button" onClick={() => void startNewSession()} disabled={busy || sessionsLoading}><Plus size={14} aria-hidden="true" />{busy ? "Creating…" : "Create new session"}</button> : <Clock3 size={18} aria-hidden="true" />}</div>
            {!selectedAgent ? <div className="playground-picker-empty"><Bot size={24} aria-hidden="true" /><strong>Select an agent</strong><span>Its sessions will appear here.</span></div> : selectedAgent.latest_version_number === 0 ? <div className="playground-picker-empty"><CircleAlert size={24} aria-hidden="true" /><strong>Publish a version first</strong><span>This agent only has mutable draft state.</span><button className="text-button" type="button" onClick={() => router.push(`/agents/${selectedAgent.id}`)}>Open agent configuration →</button></div> : sessionsLoading ? <div className="playground-picker-empty"><LoaderCircle className="spin" size={20} aria-hidden="true" /><span>Loading sessions…</span></div> : <div className="session-list" aria-label={`${selectedAgent.name} sessions`}>{sessions.length === 0 ? <div className="playground-picker-empty compact"><Clock3 size={24} aria-hidden="true" /><strong>No sessions yet</strong><span>Start a new conversation for this agent.</span><button className="button primary-button session-create-button" type="button" onClick={() => void startNewSession()} disabled={busy}><Plus size={15} aria-hidden="true" />{busy ? "Creating…" : "Create new session"}</button></div> : sessions.map((session) => <SessionItem key={session.id} session={session} selected={session.id === selectedSessionId} onSelect={() => setSelectedSessionId(session.id)} onContinue={() => router.push(`/agents/${selectedAgent.id}/playground?session_id=${session.id}`)} onRename={(title) => renameSession(session.id, title)} />)}</div>}
          </section>
        </main>
      )}
    </AppShell>
  );
}

export default function PlaygroundLauncherPage() {
  return (
    <Suspense fallback={<AppShell><section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading playground…</section></AppShell>}>
      <PlaygroundLauncherContent />
    </Suspense>
  );
}
