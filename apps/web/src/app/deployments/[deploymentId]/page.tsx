"use client";

import { useParams, useRouter } from "next/navigation";
import { AlertCircle, ArrowLeft, Check, Clipboard, Cloud, Info, KeyRound, LoaderCircle, Plus, Power, RotateCcw, ShieldCheck, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "../../../components/app-shell";
import { DeleteAction } from "../../../components/delete-action";
import { PrimarySelect } from "../../../components/primary-select";
import { PrimaryTextInput } from "../../../components/primary-text-field";
import { apiFetch, readApiError } from "../../../lib/api";
import { fetchVersions, type AgentVersionSummary } from "../../../lib/agents";
import {
  changeDeploymentVersion,
  createDeploymentApiKey,
  fetchDeployment,
  fetchDeploymentApiKeys,
  revokeDeploymentApiKey,
  setDeploymentStatus,
  type CreatedDeploymentApiKey,
  type Deployment,
  type DeploymentApiKey,
} from "../../../lib/deployments";

type Workspace = { id: string; role: "OWNER" | "MEMBER" };

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Never";
}

export default function DeploymentDetailPage() {
  const params = useParams<{ deploymentId: string }>();
  const router = useRouter();
  const deploymentId = params.deploymentId;
  const [deployment, setDeployment] = useState<Deployment | null>(null);
  const [workspaceRole, setWorkspaceRole] = useState<Workspace["role"]>("MEMBER");
  const [keys, setKeys] = useState<DeploymentApiKey[]>([]);
  const [versions, setVersions] = useState<AgentVersionSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingVersion, setSavingVersion] = useState(false);
  const [changingStatus, setChangingStatus] = useState(false);
  const [creatingKey, setCreatingKey] = useState(false);
  const [revokingKeyId, setRevokingKeyId] = useState<string | null>(null);
  const [confirmingKeyId, setConfirmingKeyId] = useState<string | null>(null);
  const [keyDialogOpen, setKeyDialogOpen] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<CreatedDeploymentApiKey | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [copiedExample, setCopiedExample] = useState(false);
  const [invocationHelpOpen, setInvocationHelpOpen] = useState(false);
  const invocationDialogRef = useRef<HTMLDialogElement>(null);
  const invocationHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const dialog = invocationDialogRef.current;
    if (!dialog) return;
    if (invocationHelpOpen && !dialog.open) {
      dialog.showModal();
      requestAnimationFrame(() => invocationHeadingRef.current?.focus());
    } else if (!invocationHelpOpen && dialog.open) dialog.close();
  }, [invocationHelpOpen]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void Promise.all([
      fetchDeployment(deploymentId),
      fetchDeploymentApiKeys(deploymentId),
      apiFetch("/v1/workspaces"),
    ]).then(async ([nextDeployment, nextKeys, workspacesResponse]) => {
      if (!workspacesResponse.ok) throw new Error(await readApiError(workspacesResponse));
      const workspaceBody = await workspacesResponse.json() as { data: Workspace[] };
      const selectedWorkspace = workspaceBody.data.find((item) => item.id === nextDeployment.workspace_id);
      if (!selectedWorkspace) throw new Error("You do not have access to this deployment workspace.");
      const nextVersions = await fetchVersions(nextDeployment.agent_id);
      if (cancelled) return;
      setDeployment(nextDeployment);
      setKeys(nextKeys);
      setWorkspaceRole(selectedWorkspace.role);
      setVersions(nextVersions);
      setSelectedVersion(nextDeployment.agent_version_id);
    }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load deployment.");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [deploymentId]);

  const versionOptions = useMemo(() => versions.map((version) => ({
    value: version.id,
    label: `Version ${version.version_number}`,
    secondary: version.change_note || new Date(version.created_at).toLocaleDateString(),
  })), [versions]);

  const closeKeyDialog = useCallback(() => {
    if (creatingKey) return;
    setKeyDialogOpen(false);
    setCreatedKey(null);
    setKeyName("");
    setCopyMessage(null);
  }, [creatingKey]);

  useEffect(() => {
    if (!keyDialogOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") closeKeyDialog();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [keyDialogOpen, closeKeyDialog]);

  async function saveVersion() {
    if (!deployment || !selectedVersion || selectedVersion === deployment.agent_version_id || savingVersion) return;
    setSavingVersion(true);
    setError(null);
    try {
      setDeployment(await changeDeploymentVersion(deployment.id, selectedVersion));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to change the pinned version.");
    } finally {
      setSavingVersion(false);
    }
  }

  async function toggleStatus() {
    if (!deployment || changingStatus) return;
    setChangingStatus(true);
    setError(null);
    try {
      setDeployment(await setDeploymentStatus(deployment.id, deployment.status === "ACTIVE" ? "DISABLED" : "ACTIVE"));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to update deployment status.");
    } finally {
      setChangingStatus(false);
    }
  }

  async function submitKey(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!deployment || !keyName.trim() || creatingKey) return;
    setCreatingKey(true);
    setError(null);
    try {
      const key = await createDeploymentApiKey(deployment.id, keyName.trim());
      setCreatedKey(key);
      const { key: rawKey, ...keyMetadata } = key;
      void rawKey;
      setKeys((current) => [keyMetadata, ...current]);
      setCopyMessage(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to create API key.");
    } finally {
      setCreatingKey(false);
    }
  }

  async function copyText(value: string, success: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(value);
      setCopyMessage(success);
      return true;
    } catch {
      setCopyMessage("Clipboard access failed. Select and copy the text manually.");
      return false;
    }
  }

  async function revokeKey(key: DeploymentApiKey) {
    setRevokingKeyId(key.id);
    setError(null);
    try {
      await revokeDeploymentApiKey(key.id);
      setKeys((current) => current.map((item) => item.id === key.id ? { ...item, revoked_at: new Date().toISOString() } : item));
      setConfirmingKeyId(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to revoke API key.");
    } finally {
      setRevokingKeyId(null);
    }
  }

  const endpoint = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/v1/deployments/${deploymentId}/runs`;
  const streamEndpoint = `${endpoint}:stream`;
  const curlExample = [
    "curl -X POST '" + endpoint + "' \\",
    "  -H 'Authorization: Bearer vf_live_REPLACE_WITH_KEY' \\",
    "  -H 'Content-Type: application/json' \\",
    "  -H 'Idempotency-Key: request-123' \\",
    `  -d '{"input":{"type":"text","text":"Hello"}}'`,
  ].join("\n");
  const continueExample = [
    `curl -X POST '${endpoint}' \\`,
    "  -H 'Authorization: Bearer vf_live_REPLACE_WITH_KEY' \\",
    "  -H 'Content-Type: application/json' \\",
    "  -H 'Idempotency-Key: request-124' \\",
    `  -d '{"input":{"type":"text","text":"Follow-up question"},"session_id":"SESSION_ID_FROM_FIRST_RESPONSE"}'`,
  ].join("\n");
  const streamExample = [
    `curl --no-buffer -X POST '${streamEndpoint}' \\`,
    "  -H 'Authorization: Bearer vf_live_REPLACE_WITH_KEY' \\",
    "  -H 'Content-Type: application/json' \\",
    "  -H 'Idempotency-Key: request-125' \\",
    `  -d '{"input":{"type":"text","text":"Hello as a stream"}}'`,
  ].join("\n");

  return <AppShell><div className="pagination-page deployment-detail-page">
    <button className="text-button" type="button" onClick={() => router.push("/deployments")}><ArrowLeft size={15} aria-hidden="true" />Deployments</button>
    {error ? <div className="form-error agent-alert" role="alert"><AlertCircle size={15} aria-hidden="true" />{error}</div> : null}
    {loading ? <section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading deployment…</section> : null}
    {!loading && deployment ? <>
      <div className="page-header deployment-detail-header"><div><p className="eyebrow">Deployment / {deployment.environment}</p><h1>{deployment.name}</h1><p className="page-description">{deployment.agent_name} · version {deployment.agent_version_number} · <code>{deployment.slug}</code></p></div><div className="deployment-header-actions"><span className={`status-badge ${deployment.status === "ACTIVE" ? "success" : "muted"}`}><span />{deployment.status === "ACTIVE" ? "Active" : "Disabled"}</span>{workspaceRole === "OWNER" ? <button className={`button ${deployment.status === "ACTIVE" ? "danger-button" : "primary-button"}`} type="button" onClick={() => void toggleStatus()} disabled={changingStatus}>{changingStatus ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : deployment.status === "ACTIVE" ? <Power size={15} aria-hidden="true" /> : <ShieldCheck size={15} aria-hidden="true" />}{deployment.status === "ACTIVE" ? "Disable" : "Enable"}</button> : null}</div></div>

      <section className="panel deployment-version-panel">
        <div className="panel-heading"><div><h2>Published version</h2><p className="panel-copy">Production runs use the version pinned here. Changing it does not mutate the agent version.</p></div><RotateCcw size={20} aria-hidden="true" /></div>
        <div className="deployment-version-controls"><label className="deployment-version-field">Version<PrimarySelect value={selectedVersion} options={versionOptions} placeholder="Choose a published version" ariaLabel="Deployment version" onChange={setSelectedVersion} disabled={workspaceRole !== "OWNER"} /></label>{workspaceRole === "OWNER" ? <button className="button primary-button" type="button" onClick={() => void saveVersion()} disabled={savingVersion || selectedVersion === deployment.agent_version_id}>{savingVersion ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : null}Change version</button> : null}</div>
      </section>

      <section className="panel deployment-key-panel">
        <div className="panel-heading"><div><h2>API keys</h2><p className="panel-copy">Keys authorize callers to run this deployment. Raw keys are shown only once.</p></div>{workspaceRole === "OWNER" ? <button className="button primary-button" type="button" onClick={() => { setKeyName(""); setCreatedKey(null); setKeyDialogOpen(true); }}><Plus size={15} aria-hidden="true" />Create key</button> : null}</div>
        {keys.length === 0 ? <div className="deployment-keys-empty"><KeyRound size={19} aria-hidden="true" /><span>No API keys have been created.</span></div> : <div className="deployment-key-list">{keys.map((key) => <article className="deployment-key-row" key={key.id}><span className="deployment-key-icon"><KeyRound size={16} aria-hidden="true" /></span><div className="deployment-key-main"><strong>{key.name}</strong><code>{key.key_prefix}••••••••</code></div><span className={`status-badge ${key.revoked_at ? "muted" : key.expires_at && new Date(key.expires_at) < new Date() ? "error" : "success"}`}><span />{key.revoked_at ? "Revoked" : key.expires_at && new Date(key.expires_at) < new Date() ? "Expired" : "Active"}</span><div className="deployment-key-meta"><small>Last used {formatDate(key.last_used_at)}</small><small>Created {formatDate(key.created_at)}</small></div>{workspaceRole === "OWNER" && !key.revoked_at ? <DeleteAction label={key.name} confirming={confirmingKeyId === key.id} busy={revokingKeyId === key.id} onRequest={() => setConfirmingKeyId(key.id)} onCancel={() => setConfirmingKeyId(null)} onConfirm={() => void revokeKey(key)} /> : null}</article>)}</div>}
      </section>

      <section className="panel deployment-invoke-panel"><div className="panel-heading"><div><div className="deployment-invoke-title"><h2>Public invocation</h2><button className="icon-button deployment-info-button" type="button" aria-label="How to call this deployment API" title="How to call this deployment API" onClick={() => setInvocationHelpOpen(true)}><Info size={16} aria-hidden="true" /></button></div><p className="panel-copy">Send a request using this deployment ID and one of its active API keys.</p></div><Cloud size={20} aria-hidden="true" /></div><div className="deployment-endpoint"><span>POST</span><code>{endpoint}</code></div><div className="deployment-code-heading"><h3>Example request</h3><button className="text-button" type="button" onClick={() => { void copyText(curlExample, "Request example copied.").then(setCopiedExample); }}><Clipboard size={14} aria-hidden="true" />{copiedExample ? "Copied" : "Copy example"}</button></div><pre className="deployment-code"><code>{curlExample}</code></pre><p className="field-helper">Keep the API key on your server. Do not embed it in browser code.</p></section>
    </> : null}

    {keyDialogOpen ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !creatingKey) closeKeyDialog(); }}><section className="modal-dialog deployment-key-dialog" role="dialog" aria-modal="true" aria-labelledby="deployment-key-dialog-title" aria-describedby="deployment-key-dialog-description">
      {createdKey ? <><div className="modal-heading"><div><p className="eyebrow">API key created</p><h2 id="deployment-key-dialog-title">Copy this key now</h2><p className="panel-copy" id="deployment-key-dialog-description">This raw key will not be shown again after closing this dialog.</p></div><button className="icon-button modal-close" type="button" aria-label="Close key dialog" onClick={closeKeyDialog}><X size={17} aria-hidden="true" /></button></div><div className="deployment-secret-value"><code>{createdKey.key}</code><button className="button subtle-button" type="button" onClick={() => void copyText(createdKey.key, "API key copied.")}><Clipboard size={15} aria-hidden="true" />Copy key</button></div><div className="deployment-secret-warning" role="note"><ShieldCheck size={16} aria-hidden="true" /><span>Store this key in your server-side secret manager. The console does not save it.</span></div>{copyMessage ? <p className="field-helper" role="status">{copyMessage}</p> : null}<div className="modal-actions"><button className="button primary-button" type="button" onClick={closeKeyDialog}><Check size={15} aria-hidden="true" />Done</button></div></> : <><div className="modal-heading"><div><p className="eyebrow">Deployment key</p><h2 id="deployment-key-dialog-title">Create API key</h2><p className="panel-copy" id="deployment-key-dialog-description">Choose a recognizable name for the service that will use this key.</p></div><button className="icon-button modal-close" type="button" aria-label="Close key dialog" onClick={closeKeyDialog} disabled={creatingKey}><X size={17} aria-hidden="true" /></button></div><form className="modal-form" onSubmit={(event) => void submitKey(event)}><label htmlFor="deployment-key-name">Key name</label><PrimaryTextInput id="deployment-key-name" value={keyName} onChange={(event) => setKeyName(event.target.value)} required maxLength={255} placeholder="Production web server" />{error ? <div className="form-error" role="alert">{error}</div> : null}<div className="modal-actions"><button className="button subtle-button" type="button" onClick={closeKeyDialog} disabled={creatingKey}>Cancel</button><button className="button primary-button" type="submit" disabled={creatingKey || !keyName.trim()}>{creatingKey ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}{creatingKey ? "Creating…" : "Create key"}</button></div></form></>}
    </section></div> : null}
    <dialog ref={invocationDialogRef} className="modal-dialog deployment-help-dialog" aria-labelledby="deployment-help-title" onClose={() => setInvocationHelpOpen(false)}><div className="modal-heading"><div><p className="eyebrow">Public API guide</p><h2 id="deployment-help-title" ref={invocationHeadingRef} tabIndex={-1}>Call this deployment</h2><p className="panel-copy">Use an active API key from your server to start a run, stream its output, or continue a conversation.</p></div><button className="icon-button modal-close" type="button" aria-label="Close API guide" onClick={() => setInvocationHelpOpen(false)}><X size={17} aria-hidden="true" /></button></div><div className="deployment-help-content"><section className="deployment-help-section"><h3>1. Run normally</h3><p>Send a POST request to the runs endpoint. The response includes a run <code>id</code> and a <code>session_id</code>.</p><pre className="deployment-code"><code>{curlExample}</code></pre></section><section className="deployment-help-section"><h3>2. Continue the conversation</h3><p>Pass the returned <code>session_id</code> in the next request body. Continue with the same API key that created the session.</p><pre className="deployment-code"><code>{continueExample}</code></pre></section><section className="deployment-help-section"><h3>3. Stream the response</h3><p>Use the <code>runs:stream</code> endpoint and <code>curl --no-buffer</code> to receive server-sent events as the run progresses. The first event includes the <code>session_id</code>.</p><pre className="deployment-code"><code>{streamExample}</code></pre></section><section className="deployment-help-notes"><h3>Things to know</h3><ul><li>Replace <code>vf_live_REPLACE_WITH_KEY</code> with an active key for this deployment. Keep it on your server; never expose it in browser code.</li><li><code>Idempotency-Key</code> is optional. Reuse the same value only when retrying the same request; use a new value for a different request.</li><li>A session belongs to the API key that created it. A different key cannot continue that session.</li><li>The deployment selects the Agent version. The request body does not accept an <code>agent_version_id</code>.</li></ul></section></div></dialog>
  </div></AppShell>;
}
