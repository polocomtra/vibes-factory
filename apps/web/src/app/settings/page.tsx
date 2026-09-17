"use client";

import {
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Check,
  Cloud,
  KeyRound,
  LoaderCircle,
  Mail,
  Plus,
  ShieldCheck,
  UserMinus,
  UsersRound,
  X,
} from "lucide-react";

import { AppShell } from "../../components/app-shell";
import { apiFetch, readApiError } from "../../lib/api";
import {
  ModelProviderId,
  testModelConnection,
} from "../../lib/model-providers";

type Workspace = {
  id: string;
  name: string;
  slug: string;
  role: "OWNER" | "MEMBER";
};

type WorkspaceMember = {
  user_id: string;
  email: string;
  role: "OWNER" | "MEMBER";
  created_at: string;
};

function initials(email: string) {
  return email.slice(0, 1).toUpperCase();
}

function joinedDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export default function SettingsPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [newWorkspaceSlug, setNewWorkspaceSlug] = useState("");
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [memberEmail, setMemberEmail] = useState("");
  const [activeTab, setActiveTab] = useState<"workspace" | "members" | "model-test">("workspace");
  const [provider, setProvider] = useState<ModelProviderId>("azure_openai");
  const [modelName, setModelName] = useState("gpt-5.6-luna");
  const [deploymentName, setDeploymentName] = useState("gpt-5.6-luna");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelTestBusy, setModelTestBusy] = useState(false);
  const [modelTestResult, setModelTestResult] = useState<Awaited<ReturnType<typeof testModelConnection>> | null>(null);
  const [modelTestError, setModelTestError] = useState<string | null>(null);
  const [memberLoading, setMemberLoading] = useState(false);
  const [memberBusyId, setMemberBusyId] = useState<string | null>(null);
  const [confirmingMemberId, setConfirmingMemberId] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const createWorkspaceButtonRef = useRef<HTMLButtonElement>(null);
  const createWorkspaceNameRef = useRef<HTMLInputElement>(null);
  const createWorkspaceDialogRef = useRef<HTMLDivElement>(null);

  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedId);
  const isOwner = selectedWorkspace?.role === "OWNER";

  async function load() {
    setLoading(true);
    setError(null);
    const response = await apiFetch("/v1/workspaces");
    if (!response.ok) {
      setError(await readApiError(response));
      setLoading(false);
      return;
    }
    const body = await response.json() as { data: Workspace[] };
    const saved = window.localStorage.getItem("vf-workspace-id");
    const id = body.data.some((workspace) => workspace.id === saved)
      ? saved
      : body.data[0]?.id ?? null;
    const workspace = body.data.find((item) => item.id === id);
    setWorkspaces(body.data);
    setSelectedId(id);
    setName(workspace?.name ?? "");
    setSlug(workspace?.slug ?? "");
    if (!id) setActiveTab("workspace");
    setLoading(false);
  }

  async function loadMembers(workspaceId: string) {
    setMemberLoading(true);
    setError(null);
    const response = await apiFetch(`/v1/workspaces/${workspaceId}/members`);
    if (!response.ok) {
      setError(await readApiError(response));
      setMemberLoading(false);
      return;
    }
    const body = await response.json() as { data: WorkspaceMember[] };
    setMembers(body.data);
    setMemberLoading(false);
  }

  useEffect(() => { void load(); }, []);

  useEffect(() => {
    if (selectedId) void loadMembers(selectedId);
    else setMembers([]);
  }, [selectedId]);

  useEffect(() => {
    if (!isCreateModalOpen) return;
    const previousOverflow = document.body.style.overflow;
    const trigger = createWorkspaceButtonRef.current;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => createWorkspaceNameRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(focusTimer);
      document.body.style.overflow = previousOverflow;
      trigger?.focus();
    };
  }, [isCreateModalOpen]);

  function handleCreateModalKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      setIsCreateModalOpen(false);
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = createWorkspaceDialogRef.current?.querySelectorAll<HTMLElement>(
      "button, input",
    );
    if (!focusable?.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setMemberBusyId("create-workspace");
    const response = await apiFetch("/v1/workspaces", {
      method: "POST",
      body: JSON.stringify({ name: newWorkspaceName, slug: newWorkspaceSlug }),
    });
    if (!response.ok) {
      setError(await readApiError(response));
      setMemberBusyId(null);
      return;
    }
    const workspace = await response.json() as Workspace;
    window.localStorage.setItem("vf-workspace-id", workspace.id);
    window.location.reload();
  }

  async function updateWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId) return;
    setError(null);
    setMessage(null);
    setMemberBusyId("update-workspace");
    const response = await apiFetch(`/v1/workspaces/${selectedId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    });
    if (!response.ok) {
      setError(await readApiError(response));
      setMemberBusyId(null);
      return;
    }
    setMessage("Workspace settings saved.");
    setMemberBusyId(null);
    window.setTimeout(() => window.location.reload(), 250);
  }

  async function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || !isOwner) return;
    setError(null);
    setMessage(null);
    setMemberBusyId("add-member");
    const response = await apiFetch(`/v1/workspaces/${selectedId}/members`, {
      method: "POST",
      body: JSON.stringify({ email: memberEmail }),
    });
    if (!response.ok) {
      setError(await readApiError(response));
      setMemberBusyId(null);
      return;
    }
    const member = await response.json() as WorkspaceMember;
    setMembers((current) => [...current, member]);
    setMemberEmail("");
    setMessage(`${member.email} is now a workspace member.`);
    setMemberBusyId(null);
  }

  async function removeMember(member: WorkspaceMember) {
    if (!selectedId || !isOwner) return;
    setError(null);
    setMessage(null);
    setMemberBusyId(member.user_id);
    const response = await apiFetch(
      `/v1/workspaces/${selectedId}/members/${member.user_id}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      setError(await readApiError(response));
      setMemberBusyId(null);
      return;
    }
    setMembers((current) => current.filter((item) => item.user_id !== member.user_id));
    setConfirmingMemberId(null);
    setMessage(`${member.email} was removed from the workspace.`);
    setMemberBusyId(null);
  }

  function selectProvider(value: ModelProviderId) {
    setProvider(value);
    setModelTestResult(null);
    setModelTestError(null);
    if (value === "azure_openai") {
      setModelName("gpt-5.6-luna");
      setDeploymentName("gpt-5.6-luna");
    } else if (value === "deepseek") {
      setModelName("deepseek-flash");
      setDeploymentName("");
    } else if (value === "google") {
      setModelName("gemini-2.5-flash");
      setDeploymentName("");
    } else {
      setModelName("gpt-4.1-mini");
      setDeploymentName("");
    }
  }

  async function submitModelTest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || !apiKey.trim()) return;
    setModelTestBusy(true);
    setModelTestResult(null);
    setModelTestError(null);
    try {
      const result = await testModelConnection(selectedId, {
        provider,
        model_name: modelName,
        deployment_name: provider === "azure_openai" ? deploymentName : undefined,
        base_url: provider === "azure_openai" && baseUrl.trim() ? baseUrl.trim() : undefined,
        api_key: apiKey,
      });
      setModelTestResult(result);
    } catch (testError) {
      setModelTestError(testError instanceof Error ? testError.message : "Connection test failed.");
    } finally {
      setApiKey("");
      setModelTestBusy(false);
    }
  }

  return <AppShell>
    <div className="page-header">
      <div>
        <p className="eyebrow">VibesFactory / Workspace</p>
        <h1>Settings</h1>
        <p className="page-description">Manage workspace identity, access, and tenant boundaries.</p>
      </div>
      <button
        ref={createWorkspaceButtonRef}
        className="button primary-button create-workspace-trigger"
        type="button"
        onClick={() => {
          setError(null);
          setMessage(null);
          setIsCreateModalOpen(true);
        }}
      >
        <Plus size={15} aria-hidden="true" />
        Create workspace
      </button>
    </div>

    <div className="settings-tabs" role="tablist" aria-label="Workspace settings">
      <button
        className={`settings-tab${activeTab === "workspace" ? " active" : ""}`}
        type="button"
        role="tab"
        aria-selected={activeTab === "workspace"}
        onClick={() => setActiveTab("workspace")}
      >
        Workspace
      </button>
      <button
        className={`settings-tab${activeTab === "members" ? " active" : ""}`}
        type="button"
        role="tab"
        aria-selected={activeTab === "members"}
        disabled={!selectedId}
        onClick={() => setActiveTab("members")}
      >
        <UsersRound size={14} aria-hidden="true" />
        Members
        {selectedId ? <span className="tab-count">{members.length}</span> : null}
      </button>
      <button
        className={`settings-tab${activeTab === "model-test" ? " active" : ""}`}
        type="button"
        role="tab"
        aria-selected={activeTab === "model-test"}
        disabled={!selectedId}
        onClick={() => setActiveTab("model-test")}
      >
        <KeyRound size={14} aria-hidden="true" />
        Test model
      </button>
    </div>

    {error ? <p className="form-error" role="alert">{error}</p> : null}
    {message ? <p className="form-success" role="status"><Check size={14} aria-hidden="true" />{message}</p> : null}

    {loading ? <section className="panel settings-loading" aria-live="polite">Loading workspace settings…</section> : null}

    {!loading && activeTab === "workspace" ? <section className="settings-grid settings-grid-single" role="tabpanel">
      <article className="panel settings-card">
        <span className="panel-kicker">Current workspace</span>
        <h2>{selectedId ? "Workspace details" : "Create your first workspace"}</h2>
        {selectedId ? <form className="settings-form" onSubmit={updateWorkspace}>
          <label htmlFor="workspace-name">Name</label>
          <input id="workspace-name" value={name} onChange={(event) => setName(event.target.value)} required />
          <label htmlFor="workspace-slug">Slug</label>
          <input id="workspace-slug" value={slug} disabled />
          <button className="button primary-button" type="submit" disabled={memberBusyId === "update-workspace"}>
            {memberBusyId === "update-workspace" ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : null}
            Save settings
          </button>
        </form> : <p className="panel-copy">Create a workspace to start isolating agents and platform resources.</p>}
      </article>
    </section> : null}

    {!loading && activeTab === "members" && selectedId ? <section className="panel members-panel" role="tabpanel">
      <div className="members-heading">
        <div>
          <span className="panel-kicker">Workspace access</span>
          <h2>Members</h2>
          <p className="panel-copy">Control who can access {selectedWorkspace?.name ?? "this workspace"}.</p>
        </div>
        <span className="status-badge info"><span />{members.length} {members.length === 1 ? "member" : "members"}</span>
      </div>

      {isOwner ? <form className="member-add-form" onSubmit={addMember}>
        <div className="member-add-copy">
          <Mail size={17} aria-hidden="true" />
          <div>
            <label htmlFor="member-email">Add existing member</label>
            <p>They must sign in to VibesFactory once before you can add them.</p>
          </div>
        </div>
        <div className="member-add-controls">
          <input id="member-email" type="email" value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} placeholder="teammate@company.com" required />
          <button className="button primary-button" type="submit" disabled={memberBusyId === "add-member"}>
            {memberBusyId === "add-member" ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}
            Add member
          </button>
        </div>
      </form> : <div className="member-readonly-note"><ShieldCheck size={16} aria-hidden="true" />You can view members, but only the workspace owner can change access.</div>}

      <div className="member-list" aria-live="polite">
        {memberLoading ? <div className="member-list-state">Loading members…</div> : null}
        {!memberLoading && members.length === 0 ? <div className="member-list-state member-empty-state"><UsersRound size={25} aria-hidden="true" /><strong>No members yet</strong><span>Add a teammate by email to start collaborating.</span></div> : null}
        {!memberLoading && members.map((member) => <div className="member-row" key={member.user_id}>
          <div className="member-avatar" aria-hidden="true">{initials(member.email)}</div>
          <div className="member-copy"><strong>{member.email}</strong><span>Joined {joinedDate(member.created_at)}</span></div>
          <span className={`member-role ${member.role.toLowerCase()}`}>
            {member.role === "OWNER" ? <ShieldCheck size={13} aria-hidden="true" /> : null}
            {member.role === "OWNER" ? "Owner" : "Member"}
          </span>
          {member.role === "OWNER" || !isOwner ? <span className="member-action-placeholder" aria-hidden="true" /> : confirmingMemberId === member.user_id ? <div className="member-confirm-actions"><button className="text-button" type="button" onClick={() => setConfirmingMemberId(null)}>Cancel</button><button className="button danger-button" type="button" disabled={memberBusyId === member.user_id} onClick={() => void removeMember(member)}>{memberBusyId === member.user_id ? <LoaderCircle className="spin" size={13} aria-hidden="true" /> : null}Remove</button></div> : <button className="icon-button danger-icon" type="button" aria-label={`Remove ${member.email}`} onClick={() => setConfirmingMemberId(member.user_id)}><UserMinus size={16} aria-hidden="true" /></button>}
        </div>)}
      </div>
    </section> : null}

    {!loading && activeTab === "model-test" && selectedId ? <section className="panel model-test-panel" role="tabpanel">
      <div className="members-heading">
        <div>
          <span className="panel-kicker">Ephemeral provider probe</span>
          <h2>Test Model Connection</h2>
          <p className="panel-copy">Verify a provider key with one low-token request. The key is cleared from this form after the test.</p>
        </div>
        <span className="status-badge info"><span />No credentials saved</span>
      </div>

      <form className="model-test-form" onSubmit={submitModelTest}>
        <div className="model-test-field-grid">
          <label htmlFor="model-test-provider">Provider
            <select id="model-test-provider" value={provider} onChange={(event) => selectProvider(event.target.value as ModelProviderId)}>
              <option value="azure_openai">Azure OpenAI</option>
              <option value="openai">OpenAI</option>
              <option value="deepseek">DeepSeek</option>
              <option value="google">Google Gemini</option>
            </select>
          </label>
          <label htmlFor="model-test-model">Model / deployment ID
            <input id="model-test-model" value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="gpt-4.1-mini" required />
          </label>
          {provider === "azure_openai" ? <label htmlFor="model-test-deployment">Azure deployment name
            <input id="model-test-deployment" value={deploymentName} onChange={(event) => setDeploymentName(event.target.value)} placeholder="gpt-5.6-luna" required />
          </label> : null}
          {provider === "azure_openai" ? <label className="model-test-wide" htmlFor="model-test-base-url">Azure base URL
            <input id="model-test-base-url" type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://resource.services.ai.azure.com/openai/v1" required />
          </label> : null}
          <label className="model-test-wide" htmlFor="model-test-api-key">API key
            <input id="model-test-api-key" type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="Enter a temporary provider key" required />
          </label>
        </div>
        <div className="model-test-actions">
          <p className="field-helper"><Cloud size={13} aria-hidden="true" /> Sent only to the selected provider through the authenticated API.</p>
          <button className="button primary-button" type="submit" disabled={modelTestBusy || !apiKey.trim()}>
            {modelTestBusy ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <KeyRound size={15} aria-hidden="true" />}
            {modelTestBusy ? "Testing…" : "Test connection"}
          </button>
        </div>
      </form>

      {modelTestError ? <div className="model-test-result failed" role="alert"><X size={16} aria-hidden="true" /><div><strong>Request failed</strong><span>{modelTestError}</span></div></div> : null}
      {modelTestResult?.status === "SUCCESS" ? <div className="model-test-result success" role="status"><Check size={16} aria-hidden="true" /><div><strong>Connection successful</strong><span>{modelTestResult.provider} · {modelTestResult.model_name} · {modelTestResult.latency_ms ?? 0} ms</span></div></div> : null}
      {modelTestResult?.status === "FAILED" && modelTestResult.error ? <div className="model-test-result failed" role="alert"><X size={16} aria-hidden="true" /><div><strong>Connection failed</strong><span>{modelTestResult.error.message}</span><small>{modelTestResult.error.code}</small></div></div> : null}
    </section> : null}

    {isCreateModalOpen ? <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) setIsCreateModalOpen(false);
      }}
    >
      <div
        ref={createWorkspaceDialogRef}
        className="modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-workspace-title"
        onKeyDown={handleCreateModalKeyDown}
      >
        <div className="modal-heading">
          <div>
            <span className="panel-kicker">New tenant boundary</span>
            <h2 id="create-workspace-title">Create workspace</h2>
            <p className="panel-copy">Give your new workspace a clear identity to keep agents and resources isolated.</p>
          </div>
          <button className="icon-button modal-close" type="button" aria-label="Close create workspace dialog" onClick={() => setIsCreateModalOpen(false)}>
            <X size={17} aria-hidden="true" />
          </button>
        </div>
        <form className="settings-form modal-form" onSubmit={createWorkspace}>
          <label htmlFor="new-workspace-name">Name</label>
          <input ref={createWorkspaceNameRef} id="new-workspace-name" value={newWorkspaceName} onChange={(event) => setNewWorkspaceName(event.target.value)} placeholder="Personal AI Lab" required />
          <label htmlFor="new-workspace-slug">Slug</label>
          <input id="new-workspace-slug" value={newWorkspaceSlug} onChange={(event) => setNewWorkspaceSlug(event.target.value)} placeholder="personal-ai-lab" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" required />
          <p className="field-helper">Use lowercase letters, numbers, and hyphens.</p>
          <div className="modal-actions">
            <button className="button secondary-button" type="button" onClick={() => setIsCreateModalOpen(false)}>Cancel</button>
            <button className="button primary-button" type="submit" disabled={memberBusyId === "create-workspace"}>
              {memberBusyId === "create-workspace" ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}
              Create workspace
            </button>
          </div>
        </form>
      </div>
    </div> : null}
  </AppShell>;
}
