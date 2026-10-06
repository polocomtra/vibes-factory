"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowRight, KeyRound, LoaderCircle, Plus, X } from "lucide-react";

import { AppShell, useSelectedWorkspaceId, useSelectedWorkspaceRole } from "../../../components/app-shell";
import { PrimarySelect, type PrimarySelectOption } from "../../../components/primary-select";
import { PrimaryTextInput } from "../../../components/primary-text-field";
import { createModelConnection, fetchModelConnections, type ModelConnection, type ModelProviderId } from "../../../lib/model-connections";

const providers: PrimarySelectOption[] = [
  { value: "azure_openai", label: "Azure OpenAI" },
  { value: "google", label: "Google Gemini" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "openrouter", label: "OpenRouter" },
];

function Catalog() {
  const workspaceId = useSelectedWorkspaceId();
  const workspaceRole = useSelectedWorkspaceRole();
  const isOwner = workspaceRole === "OWNER";
  const [items, setItems] = useState<ModelConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [provider, setProvider] = useState<ModelProviderId>("azure_openai");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true); setError(null);
    try { setItems(await fetchModelConnections(workspaceId)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load models."); }
    finally { setLoading(false); }
  }, [workspaceId]);
  useEffect(() => { void load(); }, [load]);

  function clearForm() {
    setName(""); setApiKey(""); setBaseUrl(""); setFormError(null);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId) return;
    setBusy(true); setFormError(null);
    try {
      await createModelConnection(workspaceId, {
        name, provider, api_key: apiKey,
        ...(provider === "azure_openai" ? { base_url: baseUrl } : {}),
      });
      clearForm(); setOpen(false); await load();
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "Unable to save this connection.");
    } finally { setBusy(false); }
  }

  return <>
    <div className="page-header"><div><p className="eyebrow">VibesFactory / Settings</p><h1>Model</h1><p className="page-description">Manage provider keys and make models available to your agents.</p></div>
      {isOwner ? <button className="button primary-button" type="button" onClick={() => setOpen(true)}><Plus size={15} aria-hidden="true" />Add model</button> : null}
    </div>
    {loading ? <div className="panel agent-state"><LoaderCircle className="spin" size={16} aria-hidden="true" />Loading models…</div> : null}
    {!loading && error ? <div className="panel form-error" role="alert"><p>{error}</p><button className="button secondary-button" type="button" onClick={() => void load()}>Retry</button></div> : null}
    {!loading && !error && items.length === 0 ? <div className="panel empty-state"><KeyRound size={22} aria-hidden="true" /><h2>No models configured</h2><p>{isOwner ? "Add a provider and API key to make its models available in agent settings." : "Ask a workspace owner to configure a provider for agents."}</p>{isOwner ? <button className="button primary-button" type="button" onClick={() => setOpen(true)}><Plus size={15} aria-hidden="true" />Add model</button> : null}</div> : null}
    {!loading && !error && items.length ? <div className="tools-card-grid knowledge-card-grid">{items.map((item) => <article className="tool-agent-card" key={item.id}>
      <Link className="tool-agent-card-main" href={`/settings/model-connections/${item.id}`}><div className="tool-agent-card-top"><span className="tool-agent-card-icon"><KeyRound size={17} aria-hidden="true" /></span><span className={`status-badge ${item.status === "ACTIVE" ? "success" : "muted"}`}>{item.status}</span></div><div className="tool-agent-card-title"><strong>{item.name}</strong><span>{item.provider === "google" ? "Google Gemini" : providers.find((option) => option.value === item.provider)?.label}</span></div><div className="tool-agent-card-meta">{item.base_url ?? "Provider default endpoint"}</div><span className="text-button">Model details <ArrowRight size={14} aria-hidden="true" /></span></Link>
    </article>)}</div> : null}

    {open ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) { setOpen(false); clearForm(); } }}>
      <section className="modal-dialog model-connection-dialog" role="dialog" aria-modal="true" aria-labelledby="model-connection-title" aria-describedby="model-connection-description">
        <div className="modal-heading"><div><p className="eyebrow">Encrypted provider key</p><h2 id="model-connection-title">Add model</h2><p className="panel-copy" id="model-connection-description">The provider key is encrypted in the workspace vault and never returned by the API.</p></div><button className="button secondary-button modal-close" type="button" disabled={busy} aria-label="Close dialog" onClick={() => { setOpen(false); clearForm(); }}><X size={16} aria-hidden="true" /></button></div>
        <form className="modal-form model-connection-form" onSubmit={submit}>
          <label htmlFor="model-connection-name">Display name<PrimaryTextInput id="model-connection-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={255} /></label>
          <label htmlFor="model-connection-provider">Provider<PrimarySelect id="model-connection-provider" value={provider} options={providers} placeholder="Select provider" ariaLabel="Provider" onChange={(value) => setProvider(value as ModelProviderId)} /></label>
          {provider === "azure_openai" ? <label htmlFor="model-connection-endpoint">Azure v1 endpoint<PrimaryTextInput id="model-connection-endpoint" type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://resource.openai.azure.com/openai/v1" required aria-describedby="model-connection-endpoint-help" /><small id="model-connection-endpoint-help">Use your Azure resource endpoint ending in /openai/v1.</small></label> : null}
          <label htmlFor="model-connection-key">API key<PrimaryTextInput id="model-connection-key" type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} required minLength={1} /></label>
          {formError ? <p className="form-error" role="alert">{formError}</p> : null}
          <div className="modal-actions"><button className="button secondary-button" type="button" disabled={busy} onClick={() => { setOpen(false); clearForm(); }}>Cancel</button><button className="button primary-button" type="submit" disabled={busy || !name.trim() || !apiKey.trim()}>{busy ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <KeyRound size={15} aria-hidden="true" />}{busy ? "Saving…" : "Save model"}</button></div>
        </form>
      </section>
    </div> : null}
  </>;
}

export default function ModelConnectionsPage() {
  return <AppShell><Catalog /></AppShell>;
}
