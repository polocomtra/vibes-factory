"use client";

import { Bot, Filter, LoaderCircle, Plus, Search, Sparkles, UsersRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "../../components/app-shell";
import { DeleteAction } from "../../components/delete-action";
import { PaginationControls } from "../../components/pagination-controls";
import { apiFetch, readApiError } from "../../lib/api";
import { deleteAgent, type Agent, fetchAgents } from "../../lib/agents";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };

function dateLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function AgentStatus({ status }: { status: Agent["status"] }) {
  return <span className={`status-badge ${status === "ACTIVE" ? "success" : "muted"}`}><span />{status === "ACTIVE" ? "Active" : "Archived"}</span>;
}

export default function AgentsPage() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(6);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmingAgentId, setConfirmingAgentId] = useState<string | null>(null);
  const [deletingAgentId, setDeletingAgentId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadWorkspace() {
      const response = await apiFetch("/v1/workspaces");
      if (!response.ok) {
        if (!cancelled) setError(await readApiError(response));
        return;
      }
      const body = await response.json() as { data: Workspace[] };
      const saved = window.localStorage.getItem("vf-workspace-id");
      const selected = body.data.find((item) => item.id === saved) ?? body.data[0] ?? null;
      if (!cancelled) setWorkspace(selected);
    }
    void loadWorkspace();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!workspace) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void fetchAgents(workspace.id, search, status)
      .then((items) => { if (!cancelled) setAgents(items); })
      .catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load agents."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [workspace, search, status]);

  useEffect(() => {
    setPage(1);
  }, [search, status]);

  const totalPages = Math.max(1, Math.ceil(agents.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const visibleAgents = agents.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );

  async function handleDeleteAgent(agent: Agent) {
    setDeletingAgentId(agent.id);
    setError(null);
    try {
      await deleteAgent(agent.id);
      setAgents((current) => current.filter((item) => item.id !== agent.id));
      setConfirmingAgentId(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to delete agent.");
    } finally {
      setDeletingAgentId(null);
    }
  }

  return (
    <AppShell>
      <div className="pagination-page">
        <div className="page-header">
        <div>
          <p className="eyebrow">VibesFactory / Build</p>
          <h1>Agents</h1>
          <p className="page-description">Create, configure and publish immutable agent versions.</p>
        </div>
        <button className="button primary-button" type="button" onClick={() => router.push("/agents/new")}><Plus size={16} aria-hidden="true" />New agent</button>
        </div>

      {!workspace && !loading ? (
        <section className="panel agent-empty-state">
          <Bot size={30} aria-hidden="true" />
          <h2>Create a workspace first</h2>
          <p className="panel-copy">Agents are isolated by workspace. Set up your first workspace to begin.</p>
          <button className="button primary-button" type="button" onClick={() => router.push("/settings")}>Open settings</button>
        </section>
      ) : null}

      {workspace ? <>
        <section className="agent-toolbar" aria-label="Agent filters">
          <label className="agent-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search agents</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search agents…" /></label>
          <label className="agent-filter"><Filter size={15} aria-hidden="true" /><span className="sr-only">Filter by status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="ACTIVE">Active</option><option value="ARCHIVED">Archived</option></select></label>
          <span className="agent-toolbar-meta">{agents.length} agents in {workspace.name}</span>
        </section>
        {error ? <div className="form-error agent-alert" role="alert">{error}</div> : null}
        {loading ? <section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading agents…</section> : null}
        {!loading && !error && agents.length === 0 ? <section className="panel agent-empty-state"><Sparkles size={28} aria-hidden="true" /><h2>No agents yet</h2><p className="panel-copy">Start with a focused instruction and publish your first immutable version.</p><button className="button primary-button" type="button" onClick={() => router.push("/agents/new")}><Plus size={15} aria-hidden="true" />Create agent</button></section> : null}
        {!loading && agents.length > 0 ? <>
          <section className="agent-grid">
            {visibleAgents.map((agent) => (
              <article className="agent-card" key={agent.id}>
                <button
                  className="agent-card-main"
                  type="button"
                  onClick={() => router.push(`/agents/${agent.id}`)}
                >
                  <div className="agent-card-top">
                    <span className={agent.is_supervisor ? "agent-avatar supervisor" : "agent-avatar"}>
                      {agent.is_supervisor ? <UsersRound size={17} aria-hidden="true" /> : <Bot size={17} aria-hidden="true" />}
                    </span>
                    <span className={`agent-kind-badge ${agent.is_supervisor ? "supervisor" : "utility"}`}>
                      {agent.is_supervisor ? <UsersRound size={12} aria-hidden="true" /> : <Bot size={12} aria-hidden="true" />}
                      {agent.is_supervisor ? "Supervisor" : "Utility"}
                    </span>
                    <AgentStatus status={agent.status} />
                  </div>
                  <h2>{agent.name}</h2>
                  <p>{agent.description || "No description yet."}</p>
                  <div className="agent-card-meta">
                    <span><small>Slug</small><code>{agent.slug}</code></span>
                    <span><small>Latest version</small><b>{agent.latest_version_number ? `v${agent.latest_version_number}` : "Draft only"}</b></span>
                  </div>
                </button>
                <footer>
                  <span>Updated {dateLabel(agent.updated_at)}</span>
                  <div className="card-footer-actions">
                    <span className="card-open-arrow" aria-hidden="true">→</span>
                    <DeleteAction
                      label={agent.name}
                      confirming={confirmingAgentId === agent.id}
                      busy={deletingAgentId === agent.id}
                      onRequest={() => setConfirmingAgentId(agent.id)}
                      onCancel={() => setConfirmingAgentId(null)}
                      onConfirm={() => void handleDeleteAgent(agent)}
                    />
                  </div>
                </footer>
              </article>
            ))}
          </section>
          <PaginationControls page={currentPage} pageSize={pageSize} totalItems={agents.length} onPageChange={setPage} onPageSizeChange={setPageSize} ariaLabel="Agents pagination" />
        </> : null}
      </> : null}
      </div>
    </AppShell>
  );
}
