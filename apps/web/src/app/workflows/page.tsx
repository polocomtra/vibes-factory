"use client";

import { GitBranch, LoaderCircle, Plus, Search, Workflow as WorkflowIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "../../components/app-shell";
import { DeleteAction } from "../../components/delete-action";
import { apiFetch, readApiError } from "../../lib/api";
import { createWorkflow, deleteWorkflow, fetchWorkflows, type Workflow } from "../../lib/workflows";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };

export default function WorkflowsPage() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [items, setItems] = useState<Workflow[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [confirmingWorkflowId, setConfirmingWorkflowId] = useState<string | null>(null);
  const [deletingWorkflowId, setDeletingWorkflowId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void apiFetch("/v1/workspaces").then(async (response) => {
      if (!response.ok) throw new Error(await readApiError(response));
      const body = await response.json() as { data: Workspace[] };
      const saved = window.localStorage.getItem("vf-workspace-id");
      if (!cancelled) setWorkspace(body.data.find((item) => item.id === saved) ?? body.data[0] ?? null);
    }).catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load workspaces."); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!workspace) { setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    void fetchWorkflows(workspace.id).then((next) => { if (!cancelled) setItems(next); }).catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load workflows."); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [workspace]);

  const filtered = useMemo(() => items.filter((item) => `${item.name} ${item.slug}`.toLowerCase().includes(query.toLowerCase())), [items, query]);

  async function handleCreate() {
    if (!workspace || creating) return;
    setCreating(true); setError(null);
    try {
      const slug = `workflow-${Date.now().toString(36)}`;
      const workflow = await createWorkflow(workspace.id, { name: "Untitled workflow", slug });
      router.push(`/workflows/${workflow.id}`);
    } catch (reason: unknown) { setError(reason instanceof Error ? reason.message : "Unable to create workflow."); } finally { setCreating(false); }
  }

  async function handleDelete(workflow: Workflow) {
    setDeletingWorkflowId(workflow.id);
    setError(null);
    try {
      await deleteWorkflow(workflow.id);
      setItems((current) => current.filter((item) => item.id !== workflow.id));
      setConfirmingWorkflowId(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to delete workflow.");
    } finally {
      setDeletingWorkflowId(null);
    }
  }

  return <AppShell><div className="pagination-page workflow-catalog-page">
    <div className="page-header"><div><p className="eyebrow">VibesFactory / Build</p><h1>Workflows</h1><p className="page-description">Compose durable, observable multi-agent runs from a deterministic graph.</p></div><button className="button primary-button" type="button" onClick={() => void handleCreate()} disabled={creating}><Plus size={16} aria-hidden="true" />{creating ? "Creating…" : "New workflow"}</button></div>
    {error ? <div className="form-error agent-alert" role="alert">{error}</div> : null}
    {workspace ? <section className="agent-toolbar"><label className="agent-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search workflows</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search workflows…" /></label><span className="agent-toolbar-meta">{items.length} workflows in {workspace.name}</span></section> : null}
    {loading ? <section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading workflows…</section> : null}
    {!loading && filtered.length === 0 ? <section className="panel agent-empty-state"><GitBranch size={30} aria-hidden="true" /><h2>{items.length ? "No matching workflows" : "No workflows yet"}</h2><p className="panel-copy">Start with a small deterministic flow, then add agents and tools as the run contract becomes clear.</p>{items.length === 0 ? <button className="button primary-button" type="button" onClick={() => void handleCreate()}><Plus size={15} aria-hidden="true" />Create workflow</button> : null}</section> : null}
    {!loading && filtered.length > 0 ? <section className="agent-grid workflow-grid">{filtered.map((workflow) => <article className="agent-card workflow-card" key={workflow.id}><button className="agent-card-main" type="button" onClick={() => router.push(`/workflows/${workflow.id}`)}><div className="agent-card-top"><span className="agent-avatar"><WorkflowIcon size={17} aria-hidden="true" /></span><span className={`status-badge ${workflow.status === "ACTIVE" ? "success" : "muted"}`}><span />{workflow.status === "ACTIVE" ? "Active" : "Archived"}</span></div><h2>{workflow.name}</h2><p>{workflow.description || "Deterministic workflow graph"}</p><div className="agent-card-meta"><span><small>Latest version</small><b>{workflow.latest_version_number ? `v${workflow.latest_version_number}` : "Draft only"}</b></span></div></button><footer><span>Updated {new Date(workflow.updated_at).toLocaleDateString()}</span><div className="card-footer-actions"><span className="card-open-arrow" aria-hidden="true">→</span><DeleteAction label={workflow.name} confirming={confirmingWorkflowId === workflow.id} busy={deletingWorkflowId === workflow.id} onRequest={() => setConfirmingWorkflowId(workflow.id)} onCancel={() => setConfirmingWorkflowId(null)} onConfirm={() => void handleDelete(workflow)} /></div></footer></article>)}</section> : null}
  </div></AppShell>;
}
