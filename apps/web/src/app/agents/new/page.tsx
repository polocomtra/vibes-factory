"use client";

import { ArrowLeft, Bot, LoaderCircle, Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { AppShell } from "../../../components/app-shell";
import { ModelSelect } from "../../../components/model-select";
import { apiFetch, readApiError } from "../../../lib/api";
import { fetchModels, type ModelDefinition } from "../../../lib/agents";

const defaultInstructions = "You are a helpful AI agent. Be concise, accurate, and transparent about uncertainty.";

export default function NewAgentPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [models, setModels] = useState<ModelDefinition[]>([]);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState(defaultInstructions);
  const [modelKey, setModelKey] = useState("");
  const [temperature, setTemperature] = useState("0.2");
  const [maxTokens, setMaxTokens] = useState("4096");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const saved = window.localStorage.getItem("vf-workspace-id");
    setWorkspaceId(saved);
    void fetchModels().then((items) => {
      setModels(items);
      const defaultModel = items.find((item) => item.is_default) ?? items[0];
      if (defaultModel) setModelKey(`${defaultModel.provider}:${defaultModel.name}`);
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load model catalog.")).finally(() => setLoading(false));
  }, []);

  function updateSlug(value: string) {
    setSlug(value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""));
  }

  function updateName(value: string) {
    setName(value);
    updateSlug(value);
  }

  const azureOpenAISelected = modelKey.startsWith("azure_openai:");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId) { setError("Choose a workspace before creating an agent."); return; }
    const model = models.find((item) => `${item.provider}:${item.name}` === modelKey);
    if (!model) { setError("Choose a model from the platform catalog."); return; }
    setBusy(true); setError(null);
    const config = azureOpenAISelected
      ? { max_output_tokens: Number(maxTokens) }
      : { temperature: Number(temperature), max_output_tokens: Number(maxTokens) };
    const response = await apiFetch(`/v1/workspaces/${workspaceId}/agents`, { method: "POST", body: JSON.stringify({ name, slug, description: description || null, instructions, model: { provider: model.provider, name: model.name, config } }) });
    if (!response.ok) { setError(await readApiError(response)); setBusy(false); return; }
    const agent = await response.json() as { id: string };
    router.push(`/agents/${agent.id}`);
  }

  return <AppShell><div className="page-header create-agent-header"><div><button className="text-button" type="button" onClick={() => router.push("/agents")}><ArrowLeft size={14} aria-hidden="true" />Back to agents</button><p className="eyebrow agent-eyebrow">VibesFactory / Build</p><h1>New agent</h1><p className="page-description">Define the first draft. Publish a version when the configuration is ready.</p></div><div className="header-controls agent-command-bar"><button className="button secondary-button command-button" type="button" onClick={() => router.push("/agents")}>Cancel</button><button className="button primary-button command-button" form="new-agent-form" type="submit" disabled={busy || loading}>{busy ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Save size={15} aria-hidden="true" />}Save draft</button></div></div>
    <form id="new-agent-form" className="agent-editor-layout create-agent-flow" onSubmit={submit}>
      <div className="agent-flow-intro"><span className="flow-status"><span className="status-pulse" />Draft workspace</span><p>Set the durable identity first, then shape behavior and choose the model that will power this agent.</p></div>
      <section className="panel agent-form-panel agent-flow-section"><div className="panel-heading"><div className="section-title-group"><span className="section-index">01</span><div><span className="panel-kicker">Identity</span><h2>Agent details</h2><p className="section-description">Give this agent a clear, workspace-unique identity.</p></div></div><Bot size={18} aria-hidden="true" /></div><div className="field-grid identity-field-grid"><label>Name<input value={name} onChange={(event) => updateName(event.target.value)} placeholder="Research Assistant" required /></label><label>Slug<input value={slug} readOnly aria-readonly="true" placeholder="research-assistant" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" required /><small>Generated automatically from the agent name.</small></label><label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What is this agent responsible for?" rows={3} /></label></div></section>
      <section className="panel agent-form-panel agent-flow-section"><div className="panel-heading"><div className="section-title-group"><span className="section-index">02</span><div><span className="panel-kicker">Behavior</span><h2>Instructions</h2><p className="section-description">Describe the role, tone, scope and boundaries this agent should follow.</p></div></div></div><label><span className="sr-only">System instructions</span><textarea className="instructions-editor" value={instructions} onChange={(event) => setInstructions(event.target.value)} rows={12} required /></label><div className="editor-hint"><span>Tip</span> Start with the agent’s purpose, then add response style and escalation rules.</div></section>
      <section className="panel agent-form-panel agent-flow-section"><div className="panel-heading"><div className="section-title-group"><span className="section-index">03</span><div><span className="panel-kicker">Model</span><h2>Model configuration</h2><p className="section-description">Choose a catalog model and tune its basic generation settings.</p></div></div></div>{loading ? <div className="agent-state"><LoaderCircle className="spin" size={16} aria-hidden="true" />Loading catalog…</div> : <div className="field-grid model-field-grid"><label>Model<ModelSelect models={models} value={modelKey} onChange={setModelKey} /><small>Models are supplied by the VibesFactory platform catalog.</small></label><label htmlFor="new-agent-temperature"><span>Temperature</span><input id="new-agent-temperature" type="number" inputMode="decimal" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(event.target.value)} disabled={azureOpenAISelected} aria-describedby="new-agent-temperature-helper" /><small id="new-agent-temperature-helper">{azureOpenAISelected ? "Temporarily disabled for Azure OpenAI reasoning models." : "Lower values make responses more consistent."}</small></label><label>Max output tokens<input type="number" min="1" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} /></label></div>}</section>
      {error ? <div className="form-error agent-alert" role="alert">{error}</div> : null}
    </form>
  </AppShell>;
}
