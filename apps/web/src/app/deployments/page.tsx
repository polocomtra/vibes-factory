"use client";

import { useRouter } from "next/navigation";
import { Cloud, LoaderCircle, Plus, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "../../components/app-shell";
import { PrimarySelect, type PrimarySelectOption } from "../../components/primary-select";
import { PrimaryTextInput } from "../../components/primary-text-field";
import { apiFetch, readApiError } from "../../lib/api";
import { fetchAgents, fetchVersions, type Agent, type AgentVersionSummary } from "../../lib/agents";
import {
  createDeployment,
  fetchDeployments,
  type Deployment,
} from "../../lib/deployments";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };

const environments: PrimarySelectOption[] = [
  { value: "DEVELOPMENT", label: "Development" },
  { value: "STAGING", label: "Staging" },
  { value: "PRODUCTION", label: "Production" },
];

function slugify(value: string) {
  return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function EnvironmentBadge({ environment }: { environment: Deployment["environment"] }) {
  return <span className={`deployment-environment ${environment.toLowerCase()}`}>{environment}</span>;
}

export default function DeploymentsPage() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [items, setItems] = useState<Deployment[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [agentId, setAgentId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [environment, setEnvironment] = useState("PRODUCTION");
  const [versions, setVersions] = useState<AgentVersionSummary[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void apiFetch("/v1/workspaces").then(async (response) => {
      if (!response.ok) throw new Error(await readApiError(response));
      const body = await response.json() as { data: Workspace[] };
      const savedId = window.localStorage.getItem("vf-workspace-id");
      const selected = body.data.find((item) => item.id === savedId) ?? body.data[0] ?? null;
      if (!cancelled) setWorkspace(selected);
    }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load workspace.");
    }).finally(() => {
      if (!cancelled) setWorkspaceLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!workspace) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void Promise.all([fetchDeployments(workspace.id), fetchAgents(workspace.id)])
      .then(([deployments, nextAgents]) => {
        if (cancelled) return;
        setItems(deployments);
        setAgents(nextAgents.filter((agent) => agent.status === "ACTIVE" && agent.latest_version_number > 0));
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load deployments.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [workspace]);

  useEffect(() => {
    if (!agentId) {
      setVersions([]);
      setVersionId("");
      return;
    }
    let cancelled = false;
    setVersionsLoading(true);
    void fetchVersions(agentId).then((next) => {
      if (cancelled) return;
      setVersions(next);
      setVersionId(next[0]?.id ?? "");
    }).catch((reason: unknown) => {
      if (!cancelled) setFormError(reason instanceof Error ? reason.message : "Unable to load published versions.");
    }).finally(() => { if (!cancelled) setVersionsLoading(false); });
    return () => { cancelled = true; };
  }, [agentId]);

  useEffect(() => {
    if (!createOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !creating) setCreateOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [createOpen, creating]);

  const filtered = useMemo(
    () => items.filter((item) => `${item.name} ${item.slug} ${item.agent_name} ${item.environment}`.toLowerCase().includes(query.toLowerCase())),
    [items, query],
  );

  const agentOptions = agents.map((agent) => ({
    value: agent.id,
    label: agent.name,
    secondary: `${agent.latest_version_number} published versions`,
  }));
  const versionOptions = versions.map((version) => ({
    value: version.id,
    label: `Version ${version.version_number}`,
    secondary: version.change_note || new Date(version.created_at).toLocaleDateString(),
  }));

  function resetForm() {
    setName("");
    setSlug("");
    setAgentId("");
    setVersionId("");
    setEnvironment("PRODUCTION");
    setVersions([]);
    setFormError(null);
  }

  async function submitDeployment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !versionId || creating) return;
    setCreating(true);
    setFormError(null);
    try {
      const deployment = await createDeployment(workspace.id, {
        name: name.trim(),
        slug: slug.trim() || slugify(name),
        agent_id: agentId,
        agent_version_id: versionId,
        environment: environment as Deployment["environment"],
      });
      setCreateOpen(false);
      resetForm();
      router.push(`/deployments/${deployment.id}`);
    } catch (reason: unknown) {
      setFormError(reason instanceof Error ? reason.message : "Unable to create deployment.");
    } finally {
      setCreating(false);
    }
  }

  return <AppShell><div className="pagination-page deployment-catalog-page">
    <div className="page-header">
      <div>
        <p className="eyebrow">VibesFactory / Platform</p>
        <h1>Deployments</h1>
        <p className="page-description">Publish a fixed agent version behind a stable API endpoint.</p>
      </div>
      {workspace?.role === "OWNER" ? <button className="button primary-button" type="button" onClick={() => { resetForm(); setCreateOpen(true); }}><Plus size={16} aria-hidden="true" />New deployment</button> : null}
    </div>

    {error ? <div className="form-error agent-alert" role="alert">{error}</div> : null}
    {workspace ? <section className="agent-toolbar" aria-label="Deployment filters">
      <label className="agent-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search deployments</span><PrimaryTextInput value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search deployments…" /></label>
      <span className="agent-toolbar-meta">{items.length} deployments in {workspace.name}</span>
    </section> : null}

    {loading || workspaceLoading ? <section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading deployments…</section> : null}
    {!loading && !workspaceLoading && !error && !workspace ? <section className="panel agent-empty-state">
      <Cloud size={30} aria-hidden="true" />
      <h2>No workspace available</h2>
      <p className="panel-copy">Create or join a workspace before managing deployments.</p>
    </section> : null}
    {!loading && !workspaceLoading && !error && workspace && filtered.length === 0 ? <section className="panel agent-empty-state">
      <Cloud size={30} aria-hidden="true" />
      <h2>{items.length ? "No matching deployments" : "No deployments yet"}</h2>
      <p className="panel-copy">Choose a published agent version to create a stable endpoint for your application.</p>
      {items.length === 0 && workspace?.role === "OWNER" ? <button className="button primary-button" type="button" onClick={() => { resetForm(); setCreateOpen(true); }}><Plus size={15} aria-hidden="true" />Create deployment</button> : null}
    </section> : null}

    {!loading && !workspaceLoading && filtered.length > 0 ? <section className="agent-grid deployment-grid">
      {filtered.map((item) => <article className="agent-card deployment-card" key={item.id}>
        <button className="agent-card-main" type="button" onClick={() => router.push(`/deployments/${item.id}`)}>
          <div className="agent-card-top"><span className="agent-avatar"><Cloud size={17} aria-hidden="true" /></span><EnvironmentBadge environment={item.environment} /><span className={`status-badge ${item.status === "ACTIVE" ? "success" : "muted"}`}><span />{item.status === "ACTIVE" ? "Active" : "Disabled"}</span></div>
          <h2>{item.name}</h2>
          <p>{item.agent_name}</p>
          <div className="agent-card-meta">
            <span><small>Endpoint slug</small><code>{item.slug}</code></span>
            <span><small>Published version</small><b>v{item.agent_version_number}</b></span>
          </div>
        </button>
        <footer><span>Updated {new Date(item.updated_at).toLocaleDateString()}</span><span className="card-open-arrow" aria-hidden="true">→</span></footer>
      </article>)}
    </section> : null}

    {createOpen ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !creating) setCreateOpen(false); }}>
      <section className="modal-dialog deployment-create-dialog" role="dialog" aria-modal="true" aria-labelledby="deployment-create-title" aria-describedby="deployment-create-description">
        <div className="modal-heading"><div><p className="eyebrow">Deployment</p><h2 id="deployment-create-title">Create deployment</h2><p className="panel-copy" id="deployment-create-description">Pin a published version and expose it through an API key.</p></div><button className="icon-button modal-close" type="button" aria-label="Close dialog" onClick={() => setCreateOpen(false)} disabled={creating}>×</button></div>
        <form className="modal-form deployment-form" onSubmit={(event) => void submitDeployment(event)}>
          <label htmlFor="deployment-name">Name</label>
          <PrimaryTextInput id="deployment-name" value={name} onChange={(event) => { const value = event.target.value; setName(value); setSlug(slugify(value)); }} required maxLength={255} placeholder="Research Production" />
          <label htmlFor="deployment-slug">Slug</label>
          <PrimaryTextInput id="deployment-slug" value={slug} onChange={(event) => setSlug(slugify(event.target.value))} required maxLength={100} placeholder="research-production" />
          <span className="field-helper">Unique within this workspace; used to identify this deployment in logs.</span>
          <label>Agent</label>
          <PrimarySelect value={agentId} options={agentOptions} placeholder="Choose an agent" ariaLabel="Agent" onChange={setAgentId} searchable searchPlaceholder="Search agents…" emptyMessage="No agents with a published version." />
          <label>Published version</label>
          <PrimarySelect value={versionId} options={versionOptions} placeholder={versionsLoading ? "Loading versions…" : "Choose a version"} ariaLabel="Published version" onChange={setVersionId} disabled={!agentId || versionsLoading} />
          <label>Environment</label>
          <PrimarySelect value={environment} options={environments} placeholder="Choose environment" ariaLabel="Environment" onChange={setEnvironment} />
          {formError ? <div className="form-error" role="alert">{formError}</div> : null}
          <div className="modal-actions"><button className="button subtle-button" type="button" onClick={() => setCreateOpen(false)} disabled={creating}>Cancel</button><button className="button primary-button" type="submit" disabled={creating || !name.trim() || !slug || !agentId || !versionId || versionsLoading}>{creating ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}{creating ? "Creating…" : "Create deployment"}</button></div>
        </form>
      </section>
    </div> : null}
  </div></AppShell>;
}
