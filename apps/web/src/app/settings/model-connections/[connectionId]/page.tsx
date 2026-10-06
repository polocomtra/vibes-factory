"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ArrowLeft, LoaderCircle, RotateCcw, Save, ShieldCheck, Trash2 } from "lucide-react";

import { AppShell, useSelectedWorkspaceRole } from "../../../../components/app-shell";
import { PrimarySelect, type PrimarySelectOption } from "../../../../components/primary-select";
import { PrimaryTextInput } from "../../../../components/primary-text-field";
import { apiFetch, readApiError } from "../../../../lib/api";
import { discoverModels, fetchModelConnection, renameModelConnection, revokeModelConnection, rotateModelConnectionKey, testSavedModelConnection, type DiscoveredModel, type ModelConnection } from "../../../../lib/model-connections";

function ConnectionDetail() {
  const params = useParams<{ connectionId: string }>();
  const router = useRouter();
  const isOwner = useSelectedWorkspaceRole() === "OWNER";
  const connectionId = params.connectionId;
  const [connection, setConnection] = useState<ModelConnection | null>(null);
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("");
  const [deploymentName, setDeploymentName] = useState("");
  const [models, setModels] = useState<DiscoveredModel[]>([]);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Awaited<ReturnType<typeof testSavedModelConnection>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true); setError(null);
      try {
        const saved = await fetchModelConnection(connectionId);
        if (!active) return;
        setConnection(saved); setName(saved.name);
        try { setModels(await discoverModels(connectionId)); }
        catch (reason) { setDiscoveryError(reason instanceof Error ? reason.message : "Model discovery failed."); }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load this model.");
      } finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [connectionId]);

  const modelOptions: PrimarySelectOption[] = models.map((item) => ({ value: item.name, label: item.display_name, secondary: item.name }));
  async function saveName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    try { setConnection(await renameModelConnection(connectionId, name)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to update connection."); }
    finally { setBusy(false); }
  }
  async function rotateKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    try { await rotateModelConnectionKey(connectionId, apiKey); setApiKey(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to rotate key."); }
    finally { setBusy(false); }
  }
  async function test() {
    setBusy(true); setError(null); setTestResult(null);
    try { setTestResult(await testSavedModelConnection(connectionId, { model_name: modelName, ...(connection?.provider === "azure_openai" ? { deployment_name: deploymentName } : {}) })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Connection test failed."); }
    finally { setBusy(false); }
  }
  async function revoke() {
    if (!window.confirm("Revoke this connection? Published agents that use it will stop running.")) return;
    setBusy(true); setError(null);
    try { await revokeModelConnection(connectionId); router.push("/settings/model-connections"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to revoke connection."); setBusy(false); }
  }

  return <>
    <div className="page-header"><div><Link className="text-button" href="/settings/model-connections"><ArrowLeft size={14} aria-hidden="true" />Model</Link><p className="eyebrow">VibesFactory / Settings</p><h1>{connection?.name ?? "Model"}</h1><p className="page-description">Manage this provider key and test access to its models.</p></div>{connection ? <span className={`status-badge ${connection.status === "ACTIVE" ? "success" : "muted"}`}>{connection.status}</span> : null}</div>
    {loading ? <div className="panel agent-state"><LoaderCircle className="spin" size={16} aria-hidden="true" />Loading model…</div> : null}
    {!loading && error && !connection ? <div className="panel form-error" role="alert">{error}</div> : null}
    {!loading && connection ? <div className="agent-detail-layout">
      <section className="panel agent-form-panel model-connection-detail-panel"><div className="panel-heading"><div><span className="panel-kicker">Provider</span><h2>{connection.provider === "google" ? "Google Gemini" : connection.provider}</h2><p className="section-description">{connection.base_url}</p></div><ShieldCheck size={18} aria-hidden="true" /></div>
        <form className="model-connection-details-form" onSubmit={saveName}><label htmlFor="connection-name">Name<PrimaryTextInput id="connection-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={255} disabled={!isOwner} /></label>{isOwner ? <div className="model-connection-details-actions"><button className="button secondary-button" disabled={busy || connection.status !== "ACTIVE"}><Save size={14} aria-hidden="true" />Save name</button></div> : null}</form>
      </section>
      {isOwner ? <section className="panel agent-form-panel model-connection-detail-panel"><div className="panel-heading"><div><span className="panel-kicker">Provider access</span><h2>Rotate API key</h2><p className="section-description">The current value cannot be retrieved. Enter a replacement key to rotate it.</p></div></div><form className="model-connection-details-form" onSubmit={rotateKey}><label htmlFor="connection-rotate-key">New API key<PrimaryTextInput id="connection-rotate-key" type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} required minLength={1} /></label><div className="model-connection-details-actions"><button className="button secondary-button" disabled={busy || connection.status !== "ACTIVE" || !apiKey.trim()}><RotateCcw size={14} aria-hidden="true" />Rotate key</button></div></form></section> : null}
      <section className="panel agent-form-panel model-connection-detail-panel model-connection-verification-panel"><div className="panel-heading"><div><span className="panel-kicker">Verification</span><h2>Test model</h2><p className="section-description">The probe sends one small request to the selected model.</p></div></div>
        {connection.provider !== "azure_openai" && modelOptions.length > 0 ? <div className="model-connection-model-field"><label htmlFor="test-model">Suggested model</label><PrimarySelect id="test-model" value={modelName} options={modelOptions} placeholder="Select a model" ariaLabel="Suggested model" searchable onChange={setModelName} /></div> : null}
        <label htmlFor="test-model-name">Model ID<PrimaryTextInput id="test-model-name" value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder={connection.provider === "azure_openai" ? "Azure deployment's model ID" : "provider/model-id"} required /></label>
        {connection.provider === "azure_openai" ? <label htmlFor="test-deployment">Deployment name<PrimaryTextInput id="test-deployment" value={deploymentName} onChange={(event) => setDeploymentName(event.target.value)} required /></label> : null}
        {discoveryError ? <div className="form-error" role="alert"><p>{discoveryError}</p><button className="button secondary-button" type="button" onClick={async () => { setDiscoveryError(null); try { setModels(await discoverModels(connectionId)); } catch (reason) { setDiscoveryError(reason instanceof Error ? reason.message : "Model discovery failed."); } }}>Retry model discovery</button><small>You can still enter a model ID manually.</small></div> : null}
        <button className="button secondary-button" type="button" disabled={busy || connection.status !== "ACTIVE" || !modelName.trim() || (connection.provider === "azure_openai" && !deploymentName.trim())} onClick={() => void test()}>{busy ? <LoaderCircle className="spin" size={14} aria-hidden="true" /> : <ShieldCheck size={14} aria-hidden="true" />}Test model</button>
        {testResult ? <div className={`model-test-result ${testResult.status === "SUCCESS" ? "success" : "failed"}`} role={testResult.status === "FAILED" ? "alert" : "status"}><strong>{testResult.status === "SUCCESS" ? "Model verified" : "Model test failed"}</strong><span>{testResult.error?.message ?? `${testResult.provider} · ${testResult.model_name} · ${testResult.latency_ms ?? 0} ms`}</span></div> : null}
      </section>
      {error ? <div className="form-error" role="alert">{error}</div> : null}
      {isOwner && connection.status === "ACTIVE" ? <section className="panel danger-panel"><div><strong>Revoke model access</strong><p>Agents using this provider key will fail their next model call.</p></div><button className="button danger-button" type="button" disabled={busy} onClick={() => void revoke()}><Trash2 size={14} aria-hidden="true" />Revoke</button></section> : null}
    </div> : null}
  </>;
}

export default function ModelConnectionDetailPage() {
  return <AppShell><ConnectionDetail /></AppShell>;
}
