"use client";

import { GitBranch, LoaderCircle, Plus, Search, Workflow as WorkflowIcon, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

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
  const [createOpen, setCreateOpen] = useState(false);
  const [workflowName, setWorkflowName] = useState("");
  const [workflowDescription, setWorkflowDescription] = useState("");
  const createDialogRef = useRef<HTMLDialogElement>(null);
  const createHeadingRef = useRef<HTMLHeadingElement>(null);
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

  useEffect(() => {
    const dialog = createDialogRef.current;
    if (createOpen && dialog && !dialog.open) {
      dialog.showModal();
      requestAnimationFrame(() => createHeadingRef.current?.focus());
    }
    if (!createOpen && dialog?.open) dialog.close();
  }, [createOpen]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || creating) return;
    setCreating(true); setError(null);
    try {
      const name = workflowName.trim();
      const slug = `${name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "workflow"}-${Date.now().toString(36)}`;
      const workflow = await createWorkflow(workspace.id, { name, slug, description: workflowDescription.trim() || undefined });
      router.push(`/workflows/${workflow.id}`);
    } catch (reason: unknown) { setError(reason instanceof Error ? reason.message : "Unable to create workflow."); } finally { setCreating(false); }
  }

  function openCreateDialog() {
    setWorkflowName("");
    setWorkflowDescription("");
    setError(null);
    setCreateOpen(true);
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
    <div className="page-header"><div><p className="eyebrow">VibesFactory / Build</p><h1>Workflows</h1><p className="page-description">Compose durable, observable multi-agent runs from a deterministic graph.</p></div><button className="button primary-button" type="button" onClick={openCreateDialog} disabled={!workspace}><Plus size={16} aria-hidden="true" />New workflow</button></div>
    {error ? <div className="form-error agent-alert" role="alert">{error}</div> : null}
    {workspace ? <section className="agent-toolbar"><label className="agent-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search workflows</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search workflows…" /></label><span className="agent-toolbar-meta">{items.length} workflows in {workspace.name}</span></section> : null}
    {loading ? <section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading workflows…</section> : null}
    {!loading && filtered.length === 0 ? <section className="panel agent-empty-state"><GitBranch size={30} aria-hidden="true" /><h2>{items.length ? "No matching workflows" : "No workflows yet"}</h2><p className="panel-copy">Start with a small deterministic flow, then add agents and tools as the run contract becomes clear.</p>{items.length === 0 ? <button className="button primary-button" type="button" onClick={openCreateDialog} disabled={!workspace}><Plus size={15} aria-hidden="true" />Create workflow</button> : null}</section> : null}
    {!loading && filtered.length > 0 ? <section className="agent-grid workflow-grid">{filtered.map((workflow) => <article className="agent-card workflow-card" key={workflow.id}><button className="agent-card-main" type="button" onClick={() => router.push(`/workflows/${workflow.id}`)}><div className="agent-card-top"><span className="agent-avatar"><WorkflowIcon size={17} aria-hidden="true" /></span><span className={`status-badge ${workflow.status === "ACTIVE" ? "success" : "muted"}`}><span />{workflow.status === "ACTIVE" ? "Active" : "Archived"}</span></div><h2>{workflow.name}</h2><p>{workflow.description || "Deterministic workflow graph"}</p><div className="agent-card-meta"><span><small>Latest version</small><b>{workflow.latest_version_number ? `v${workflow.latest_version_number}` : "Draft only"}</b></span></div></button><footer><span>Updated {new Date(workflow.updated_at).toLocaleDateString()}</span><div className="card-footer-actions"><span className="card-open-arrow" aria-hidden="true">→</span><DeleteAction label={workflow.name} confirming={confirmingWorkflowId === workflow.id} busy={deletingWorkflowId === workflow.id} onRequest={() => setConfirmingWorkflowId(workflow.id)} onCancel={() => setConfirmingWorkflowId(null)} onConfirm={() => void handleDelete(workflow)} /></div></footer></article>)}</section> : null}
  </div><dialog ref={createDialogRef} className="feature-help-dialog workflow-create-dialog" aria-labelledby="workflow-create-title" onClose={() => setCreateOpen(false)}><header className="feature-help-header"><div><p className="eyebrow">NEW WORKFLOW</p><h2 id="workflow-create-title" ref={createHeadingRef} tabIndex={-1}>Create a workflow</h2><p className="panel-copy">Give this workflow a clear name. You can configure its graph next.</p></div><button className="icon-button modal-close" type="button" aria-label="Close workflow creation" onClick={() => setCreateOpen(false)} disabled={creating}><X size={17} aria-hidden="true" /></button></header><form className="feature-help-body workflow-create-form" onSubmit={(event) => void handleCreate(event)}><label htmlFor="workflow-name">Workflow name</label><input id="workflow-name" className="text-input" value={workflowName} onChange={(event) => setWorkflowName(event.target.value)} maxLength={160} required placeholder="Customer support triage" /><label htmlFor="workflow-description">Description <span>(optional)</span></label><textarea id="workflow-description" className="text-input" value={workflowDescription} onChange={(event) => setWorkflowDescription(event.target.value)} maxLength={1000} rows={3} placeholder="What should this workflow coordinate?" />{error ? <div className="form-error" role="alert">{error}</div> : null}<div className="modal-actions"><button className="button subtle-button" type="button" onClick={() => setCreateOpen(false)} disabled={creating}>Cancel</button><button className="button primary-button" type="submit" disabled={creating || !workflowName.trim()}>{creating ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}{creating ? "Creating…" : "Create workflow"}</button></div></form></dialog></AppShell>;
}
