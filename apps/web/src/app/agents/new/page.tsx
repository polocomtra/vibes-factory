"use client";

import { ArrowLeft, Bot, LoaderCircle, Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { AppShell } from "../../../components/app-shell";
import { apiFetch, readApiError } from "../../../lib/api";
import { ModelConnectionPicker } from "../../../components/model-connection-picker";
import { fetchAgentTemplates, type AgentTemplate, type ModelConfiguration } from "../../../lib/agents";

const defaultInstructions = "You are a helpful AI agent. Be concise, accurate, and transparent about uncertainty.";

export default function NewAgentPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState(defaultInstructions);
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [model, setModel] = useState<ModelConfiguration>({ provider: "azure_openai", name: "gpt-6-luna", connection_id: null, deployment_name: null, config: {}, reasoning_options: {}, provider_options: {} });
  const [temperature, setTemperature] = useState("0.2");
  const [maxTokens, setMaxTokens] = useState("4096");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const saved = window.localStorage.getItem("vf-workspace-id");
    setWorkspaceId(saved);
    setLoading(false);
    void fetchAgentTemplates().then(setTemplates).catch((cause: unknown) => {
      setTemplateError(cause instanceof Error ? cause.message : "Templates could not be loaded.");
    });
  }, []);

  function updateSlug(value: string) {
    setSlug(value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""));
  }

  function updateName(value: string) {
    setName(value);
    updateSlug(value);
  }

  const azureOpenAISelected = model.provider === "azure_openai";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId) { setError("Choose a workspace before creating an agent."); return; }
    if (!model.name.trim()) { setError("Enter or choose a model ID."); return; }
    setBusy(true); setError(null);
    const config = azureOpenAISelected
      ? { ...model.config, max_output_tokens: Number(maxTokens) }
      : { temperature: Number(temperature), max_output_tokens: Number(maxTokens) };
    const selectedTemplate = templates.find((template) => template.id === templateId);
    const response = await apiFetch(`/v1/workspaces/${workspaceId}/agents`, { method: "POST", body: JSON.stringify({ name, slug, description: description || null, instructions, model: { ...model, config }, ...(selectedTemplate ? { template_id: selectedTemplate.id, template_version: selectedTemplate.version } : {}) }) });
    if (!response.ok) { setError(await readApiError(response)); setBusy(false); return; }
    const agent = await response.json() as { id: string };
    router.push(`/agents/${agent.id}`);
  }

  return <AppShell><div className="page-header create-agent-header"><div><button className="text-button" type="button" onClick={() => router.push("/agents")}><ArrowLeft size={14} aria-hidden="true" />Back to agents</button><p className="eyebrow agent-eyebrow">VibesFactory / Build</p><h1>New agent</h1><p className="page-description">Define the first draft. Publish a version when the configuration is ready.</p></div><div className="header-controls agent-command-bar"><button className="button secondary-button command-button" type="button" onClick={() => router.push("/agents")}>Cancel</button><button className="button primary-button command-button" form="new-agent-form" type="submit" disabled={busy || loading}>{busy ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Save size={15} aria-hidden="true" />}Save draft</button></div></div>
    <form id="new-agent-form" className="agent-editor-layout create-agent-flow" onSubmit={submit}>
      <div className="agent-flow-intro"><span className="flow-status"><span className="status-pulse" />Draft workspace</span><p>Set the durable identity first, then shape behavior and choose the model that will power this agent.</p></div>
      <section className="panel agent-form-panel agent-flow-section" aria-labelledby="template-heading"><div className="panel-heading"><div className="section-title-group"><span className="section-index">00</span><div><span className="panel-kicker">Starting point</span><h2 id="template-heading">Choose a template</h2><p className="section-description">Templates create editable drafts. They never publish an agent automatically.</p></div></div></div><label htmlFor="agent-template">Agent template</label><select id="agent-template" value={templateId ?? "scratch"} onChange={(event) => setTemplateId(event.target.value === "scratch" ? null : event.target.value)}><option value="scratch">Start from scratch</option>{templates.map((template) => <option key={`${template.id}:${template.version}`} value={template.id}>{template.name} · v{template.version}</option>)}</select>{templateError ? <p className="field-error" role="status">{templateError}</p> : null}{templateId ? (() => { const selected = templates.find((template) => template.id === templateId); return selected ? <div className="template-preview"><p>{selected.description}</p><div className="template-chips">{selected.capabilities.map((capability) => <span key={capability}>{capability.replaceAll("_", " ")}</span>)}</div><small>{selected.runtime_config.max_model_calls} model calls · {selected.runtime_config.max_tool_calls} tool calls · {selected.runtime_config.timeout_seconds}s timeout. You can edit these defaults before publishing.</small></div> : <p className="panel-copy">{templateError ? "Template details could not be loaded." : "Loading template details…"}</p>; })() : null}</section>
      <section className="panel agent-form-panel agent-flow-section"><div className="panel-heading"><div className="section-title-group"><span className="section-index">01</span><div><span className="panel-kicker">Identity</span><h2>Agent details</h2><p className="section-description">Give this agent a clear, workspace-unique identity.</p></div></div><Bot size={18} aria-hidden="true" /></div><div className="field-grid identity-field-grid"><label>Name<input value={name} onChange={(event) => updateName(event.target.value)} placeholder="Research Assistant" required /></label><label>Slug<input value={slug} readOnly aria-readonly="true" placeholder="research-assistant" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" required /><small>Generated automatically from the agent name.</small></label><label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What is this agent responsible for?" rows={3} /></label></div></section>
      {!templateId ? <section className="panel agent-form-panel agent-flow-section"><div className="panel-heading"><div className="section-title-group"><span className="section-index">02</span><div><span className="panel-kicker">Behavior</span><h2>Instructions</h2><p className="section-description">Describe the role, tone, scope and boundaries this agent should follow.</p></div></div></div><label><span className="sr-only">System instructions</span><textarea className="instructions-editor" value={instructions} onChange={(event) => setInstructions(event.target.value)} rows={12} required /></label><div className="editor-hint"><span>Tip</span> Start with the agent’s purpose, then add response style and escalation rules.</div></section> : null}
      <section className="panel agent-form-panel agent-flow-section"><div className="panel-heading"><div className="section-title-group"><span className="section-index">03</span><div><span className="panel-kicker">Model</span><h2>Model configuration</h2><p className="section-description">Choose a platform model or a workspace connection and model ID.</p></div></div></div><div className="field-grid model-field-grid"><ModelConnectionPicker workspaceId={workspaceId} value={model} onChange={setModel} /><label htmlFor="new-agent-temperature"><span>Temperature</span><input id="new-agent-temperature" type="number" inputMode="decimal" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(event.target.value)} disabled={azureOpenAISelected} aria-describedby="new-agent-temperature-helper" /><small id="new-agent-temperature-helper">{azureOpenAISelected ? "Disabled for the selected Azure model." : "Lower values make responses more consistent."}</small></label><label>Max output tokens<input type="number" min="1" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} /></label></div></section>
      {error ? <div className="form-error agent-alert" role="alert">{error}</div> : null}
    </form>
  </AppShell>;
}
