"use client";

import { ArrowLeft, Check, ChevronDown, Clipboard, Code2, GitBranch, LoaderCircle, Play, Save, ShieldCheck, Sparkles, X } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "../../../components/app-shell";
import { ModelSelect } from "../../../components/model-select";
import { apiFetch, readApiError } from "../../../lib/api";
import { fetchAgent, fetchDraft, fetchModels, fetchVersion, fetchVersions, type Agent, type AgentDraft, type AgentVersion, type AgentVersionSummary, type ModelDefinition } from "../../../lib/agents";

function dateLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function initialDraft(): AgentDraft {
  return { agent_id: "", instructions: "", model: { provider: "", name: "", config: {}, reasoning_options: {}, provider_options: {} }, runtime_config: { max_steps: 20, max_model_calls: 10, max_tool_calls: 10, max_child_runs: 5, max_agent_depth: 3, max_total_tokens: 100000, timeout_seconds: 120 }, memory_config: { enabled: false }, updated_at: "" };
}

export default function AgentDetailPage() {
  const params = useParams<{ agentId: string }>();
  const router = useRouter();
  const agentId = params.agentId;
  const [agent, setAgent] = useState<Agent | null>(null);
  const [draft, setDraft] = useState<AgentDraft>(initialDraft);
  const [models, setModels] = useState<ModelDefinition[]>([]);
  const [versions, setVersions] = useState<AgentVersionSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<AgentVersion | null>(null);
  const [tab, setTab] = useState<"configuration" | "versions">("configuration");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"save" | "publish" | "metadata" | null>(null);
  const [dirty, setDirty] = useState(false);
  const [changeNote, setChangeNote] = useState("");
  const [runtimeOpen, setRuntimeOpen] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [agentData, draftData, modelData, versionData] = await Promise.all([fetchAgent(agentId), fetchDraft(agentId), fetchModels(), fetchVersions(agentId)]);
      setAgent(agentData); setName(agentData.name); setDescription(agentData.description ?? ""); setDraft(draftData); setModels(modelData); setVersions(versionData); setSelectedVersion(null); setDirty(false);
    } catch (reason: unknown) { setError(reason instanceof Error ? reason.message : "Unable to load agent."); }
    finally { setLoading(false); }
  }, [agentId]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!publishOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setPublishOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [publishOpen]);

  function updateDraft(next: AgentDraft) { setDraft(next); setDirty(true); setMessage(null); }

  async function saveDraft() {
    setBusy("save"); setError(null); setMessage(null);
    const model = draft.model.provider === "azure_openai"
      ? { ...draft.model, config: { max_output_tokens: draft.model.config.max_output_tokens ?? 4096 } }
      : draft.model;
    const response = await apiFetch(`/v1/agents/${agentId}/draft`, { method: "PATCH", body: JSON.stringify({ instructions: draft.instructions, model, runtime_config: draft.runtime_config, memory_config: draft.memory_config }) });
    if (!response.ok) { setError(await readApiError(response)); setBusy(null); return; }
    setDraft(await response.json() as AgentDraft); setDirty(false); setMessage("Draft saved."); setBusy(null);
  }

  async function saveMetadata() {
    setBusy("metadata"); setError(null); setMessage(null);
    const response = await apiFetch(`/v1/agents/${agentId}`, { method: "PATCH", body: JSON.stringify({ name, description: description || null }) });
    if (!response.ok) { setError(await readApiError(response)); setBusy(null); return; }
    setAgent(await response.json() as Agent); setMessage("Agent details saved."); setBusy(null);
  }

  async function publish() {
    setBusy("publish"); setError(null); setMessage(null);
    const response = await apiFetch(`/v1/agents/${agentId}/versions`, { method: "POST", body: JSON.stringify({ change_note: changeNote || null }) });
    if (!response.ok) { setError(await readApiError(response)); setBusy(null); return; }
    setChangeNote(""); setMessage("Version published."); setBusy(null); await load(); setTab("versions");
  }

  async function selectVersion(version: AgentVersionSummary) {
    setError(null);
    try { setSelectedVersion(await fetchVersion(agentId, version.id)); }
    catch (reason: unknown) { setError(reason instanceof Error ? reason.message : "Unable to load version."); }
  }

  function updateRuntime(key: keyof AgentDraft["runtime_config"], value: string) {
    updateDraft({ ...draft, runtime_config: { ...draft.runtime_config, [key]: Number(value) } });
  }

  useEffect(() => {
    if (tab !== "versions" || selectedVersion || versions.length === 0) return;
    let cancelled = false;
    setError(null);
    void fetchVersion(agentId, versions[0].id)
      .then((version) => {
        if (!cancelled) setSelectedVersion(version);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load version.");
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, tab, versions, selectedVersion]);

  if (loading) return <AppShell><section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading agent…</section></AppShell>;
  if (!agent) return <AppShell><section className="panel agent-empty-state"><h2>Agent unavailable</h2><p className="panel-copy">{error || "This agent could not be found."}</p><button className="button secondary-button" type="button" onClick={() => router.push("/agents")}>Back to agents</button></section></AppShell>;

  return <AppShell><div className="page-header agent-detail-header"><div><button className="text-button" type="button" onClick={() => router.push("/agents")}><ArrowLeft size={14} aria-hidden="true" />Back to agents</button><p className="eyebrow agent-eyebrow">VibesFactory / Agent control plane</p><div className="agent-title-row"><span className="agent-avatar large"><BotIcon /></span><div><h1>{agent.name}</h1><p className="page-description"><code>{agent.slug}</code> · {agent.status === "ACTIVE" ? "Active" : "Archived"}</p></div></div></div><div className="header-controls agent-command-bar"><span className={`status-badge ${agent.status === "ACTIVE" ? "success" : "muted"}`}><span />{agent.latest_version_number ? `v${agent.latest_version_number} published` : "Draft only"}</span><button className="button secondary-button command-button" type="button" onClick={() => router.push(`/agents/${agentId}/playground`)} disabled={agent.latest_version_number === 0}><Play size={15} aria-hidden="true" />Open playground</button><button className="button secondary-button command-button" type="button" onClick={() => void saveDraft()} disabled={!dirty || busy !== null} aria-label="Save agent draft">{busy === "save" ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Save size={15} aria-hidden="true" />}Save draft</button><button className="button primary-button command-button" type="button" onClick={() => setPublishOpen(true)} disabled={busy !== null || dirty || agent.status === "ARCHIVED"} title={dirty ? "Save the draft before publishing." : undefined}><GitBranch size={15} aria-hidden="true" />Publish agent</button></div></div>
    <section className="agent-detail-tabs" role="tablist"><button className={tab === "configuration" ? "settings-tab active" : "settings-tab"} type="button" role="tab" aria-selected={tab === "configuration"} onClick={() => setTab("configuration")}><Code2 size={15} aria-hidden="true" />Configuration{dirty ? <span className="tab-count">*</span> : null}</button><button className={tab === "versions" ? "settings-tab active" : "settings-tab"} type="button" role="tab" aria-selected={tab === "versions"} onClick={() => setTab("versions")}><GitBranch size={15} aria-hidden="true" />Versions<span className="tab-count">{versions.length}</span></button></section>
    {error ? <div className="form-error agent-alert agent-detail-alert" role="alert">{error}</div> : null}{message ? <div className="form-success agent-alert agent-detail-alert" role="status"><Check size={14} aria-hidden="true" />{message}</div> : null}
    {tab === "configuration" ? <main className="agent-detail-layout"><section className="panel agent-form-panel"><div className="panel-heading"><div><span className="panel-kicker">Identity</span><h2>Agent details</h2></div><ShieldCheck size={18} aria-hidden="true" /></div><div className="field-grid"><label>Name<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>Slug<input value={agent.slug} disabled /></label></div><label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} /></label><div className="panel-inline-actions"><span className="field-helper">Metadata changes do not create a new version.</span><button className="button secondary-button" type="button" onClick={() => void saveMetadata()} disabled={busy !== null}>{busy === "metadata" ? <LoaderCircle className="spin" size={14} aria-hidden="true" /> : <Save size={14} aria-hidden="true" />}Save details</button></div></section>
      <section className="panel agent-form-panel"><div className="panel-heading"><div><span className="panel-kicker">Behavior</span><h2>Instructions</h2></div></div><textarea className="instructions-editor" value={draft.instructions} onChange={(event) => updateDraft({ ...draft, instructions: event.target.value })} rows={14} /></section>
      <section className="panel agent-form-panel"><div className="panel-heading"><div><span className="panel-kicker">Model</span><h2>Model configuration</h2></div></div><div className="field-grid"><label>Model<ModelSelect models={models} value={`${draft.model.provider}:${draft.model.name}`} onChange={(value) => { const model = models.find((item) => `${item.provider}:${item.name}` === value); if (model) { const config = { ...draft.model.config }; if (model.provider === "azure_openai") delete config.temperature; updateDraft({ ...draft, model: { ...draft.model, provider: model.provider, name: model.name, config } }); } }} /></label><label htmlFor="agent-temperature"><span>Temperature</span><input id="agent-temperature" type="number" inputMode="decimal" min="0" max="2" step="0.1" value={String(draft.model.config.temperature ?? 0.2)} disabled={draft.model.provider === "azure_openai"} aria-describedby="agent-temperature-helper" onChange={(event) => updateDraft({ ...draft, model: { ...draft.model, config: { ...draft.model.config, temperature: Number(event.target.value) } } })} /><small id="agent-temperature-helper">{draft.model.provider === "azure_openai" ? "Temporarily disabled for Azure OpenAI reasoning models." : "Lower values make responses more consistent."}</small></label><label>Max output tokens<input type="number" min="1" value={String(draft.model.config.max_output_tokens ?? 4096)} onChange={(event) => updateDraft({ ...draft, model: { ...draft.model, config: { ...draft.model.config, max_output_tokens: Number(event.target.value) } } })} /></label></div></section>
      <section className="panel agent-form-panel runtime-panel"><button className="runtime-accordion-trigger" type="button" aria-expanded={runtimeOpen} aria-controls="runtime-config-content" onClick={() => setRuntimeOpen((open) => !open)}><span><span className="panel-kicker">Execution</span><strong>Runtime configuration</strong><small>Limits for steps, model calls, tools and timeouts.</small></span><span className="runtime-accordion-meta"><span className="code-hint">V1</span><ChevronDown className={runtimeOpen ? "accordion-chevron open" : "accordion-chevron"} size={18} aria-hidden="true" /></span></button>{runtimeOpen ? <div className="runtime-grid" id="runtime-config-content">{(["max_steps", "max_model_calls", "max_tool_calls", "max_child_runs", "max_agent_depth", "max_total_tokens", "timeout_seconds"] as const).map((key) => <label key={key}>{key.replaceAll("_", " ")}<input type="number" min="0" value={String(draft.runtime_config[key])} onChange={(event) => updateRuntime(key, event.target.value)} /></label>)}</div> : null}</section>
      <section className="panel agent-form-panel"><div className="panel-heading"><div><span className="panel-kicker">Memory</span><h2>Memory configuration</h2></div><span className="status-badge muted">Phase 2 placeholder</span></div><label className="toggle-row"><input type="checkbox" checked={draft.memory_config.enabled} onChange={(event) => updateDraft({ ...draft, memory_config: { ...draft.memory_config, enabled: event.target.checked } })} /><span className="toggle-control" aria-hidden="true"><span /></span><span className="toggle-copy"><strong>Enable long-term memory</strong><small>Persistence and retrieval arrive in a later runtime milestone.</small></span></label></section>
    </main> : <div className="versions-layout"><section className="panel versions-list-panel"><div className="panel-heading"><div><span className="panel-kicker">Immutable history</span><h2>Published versions</h2></div><span className="code-hint">{versions.length} TOTAL</span></div>{versions.length === 0 ? <div className="agent-state"><GitBranch size={18} aria-hidden="true" />No versions published yet.</div> : <div className="version-list">{versions.map((version) => <button className={selectedVersion?.id === version.id ? "version-row selected" : "version-row"} type="button" key={version.id} onClick={() => void selectVersion(version)}><span className="version-number">v{version.version_number}</span><span><strong>{version.change_note || "Configuration snapshot"}</strong><small>{dateLabel(version.created_at)}</small></span><span>→</span></button>)}</div>}</section><section className="panel version-inspector">{selectedVersion ? <><div className="panel-heading"><div><span className="panel-kicker">Read-only snapshot</span><h2>Version {selectedVersion.version_number}</h2></div><span className="status-badge success"><span />Immutable</span></div><div className="snapshot-meta"><span>Model <b>{selectedVersion.model.name}</b></span><span>Provider <b>{selectedVersion.model.provider}</b></span><span>Published <b>{dateLabel(selectedVersion.created_at)}</b></span></div><h3>Instructions</h3><pre>{selectedVersion.instructions}</pre><h3>Runtime snapshot</h3><pre>{JSON.stringify(selectedVersion.snapshot, null, 2)}</pre><button className="button secondary-button" type="button" onClick={() => navigator.clipboard?.writeText(JSON.stringify(selectedVersion.snapshot, null, 2))}><Clipboard size={14} aria-hidden="true" />Copy snapshot</button></> : <div className="agent-empty-state compact"><GitBranch size={24} aria-hidden="true" /><h2>Select a version</h2><p className="panel-copy">Inspect the immutable instructions, model and runtime snapshot.</p></div>}</section></div>}
    {publishOpen ? <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPublishOpen(false); }}><section className="modal-dialog publish-dialog" role="dialog" aria-modal="true" aria-labelledby="publish-dialog-title" aria-describedby="publish-dialog-copy"><div className="modal-heading"><div><span className="panel-kicker">Release</span><h2 id="publish-dialog-title">Publish agent</h2><p id="publish-dialog-copy" className="panel-copy">Create an immutable runtime snapshot from the saved draft.</p></div><button className="icon-button modal-close" type="button" aria-label="Close publish dialog" onClick={() => setPublishOpen(false)}><X size={16} aria-hidden="true" /></button></div><div className="publish-summary"><span><strong>Target version</strong><b>v{agent.latest_version_number + 1}</b></span><span><strong>Last saved</strong><b>{draft.updated_at ? dateLabel(draft.updated_at) : "Not saved yet"}</b></span></div><label className="publish-note-field">Change note <textarea value={changeNote} onChange={(event) => setChangeNote(event.target.value)} rows={3} placeholder="Describe what changed (optional)" /></label><p className="field-helper">Publishing freezes the current draft. Save any pending edits before publishing.</p><div className="modal-actions"><button className="button secondary-button" type="button" onClick={() => setPublishOpen(false)}>Cancel</button><button className="button primary-button" type="button" onClick={() => { setPublishOpen(false); void publish(); }} disabled={busy !== null}><Sparkles size={15} aria-hidden="true" />Publish version</button></div></section></div> : null}
  </AppShell>;
}

function BotIcon() { return <BotGlyph />; }
function BotGlyph() { return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="4" y="6" width="16" height="13" rx="3" /><path d="M12 3v3M8 12h.01M16 12h.01M8 16h8" /></svg>; }
