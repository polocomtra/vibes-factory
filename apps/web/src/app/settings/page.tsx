"use client";

import {
    FormEvent,
    KeyboardEvent as ReactKeyboardEvent,
    useEffect,
    useRef,
    useState,
} from "react";
import {
    Building2,
    Check,
    Cloud,
    Eye,
    EyeOff,
    KeyRound,
    LockKeyhole,
    LoaderCircle,
    Plus,
    RotateCcw,
    ShieldCheck,
    Trash2,
    UserMinus,
    UsersRound,
    X,
    type LucideIcon,
} from "lucide-react";

import { AppShell } from "../../components/app-shell";
import { PrimarySelect, type PrimarySelectOption } from "../../components/primary-select";
import { PrimaryTextInput } from "../../components/primary-text-field";
import { apiFetch, readApiError } from "../../lib/api";
import {
    createCredential,
    fetchCredentials,
    revokeCredential,
    rotateCredential,
    type Credential,
} from "../../lib/credentials";
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

type SettingsTab = "workspace" | "members" | "model-test" | "credentials";

const settingsTabs: Array<{
    id: SettingsTab;
    label: string;
    description: string;
    icon: LucideIcon;
}> = [
    {
        id: "workspace",
        label: "Workspace",
        description: "Name and identity",
        icon: Building2,
    },
    {
        id: "members",
        label: "Members",
        description: "People and access",
        icon: UsersRound,
    },
    {
        id: "model-test",
        label: "Test model",
        description: "Provider connection",
        icon: Cloud,
    },
    {
        id: "credentials",
        label: "Credentials",
        description: "Encrypted secrets",
        icon: LockKeyhole,
    },
];

const modelProviderOptions: PrimarySelectOption[] = [
    { value: "azure_openai", label: "Azure OpenAI" },
    { value: "openai", label: "OpenAI" },
    { value: "deepseek", label: "DeepSeek" },
    { value: "google", label: "Google Gemini" },
];

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
    const [credentials, setCredentials] = useState<Credential[]>([]);
    const [memberEmail, setMemberEmail] = useState("");
    const [activeTab, setActiveTab] = useState<SettingsTab>("workspace");
    const [provider, setProvider] = useState<ModelProviderId>("azure_openai");
    const [modelName, setModelName] = useState("gpt-6-luna");
    const [deploymentName, setDeploymentName] = useState("gpt-6-luna");
    const [baseUrl, setBaseUrl] = useState("");
    const [apiKey, setApiKey] = useState("");
    const [modelTestBusy, setModelTestBusy] = useState(false);
    const [modelTestResult, setModelTestResult] = useState<Awaited<
        ReturnType<typeof testModelConnection>
    > | null>(null);
    const [modelTestError, setModelTestError] = useState<string | null>(null);
    const [memberLoading, setMemberLoading] = useState(false);
    const [credentialLoading, setCredentialLoading] = useState(false);
    const [credentialBusyId, setCredentialBusyId] = useState<string | null>(
        null,
    );
    const [credentialModal, setCredentialModal] = useState<
        "create" | "rotate" | null
    >(null);
    const [credentialModalId, setCredentialModalId] = useState<string | null>(
        null,
    );
    const [credentialName, setCredentialName] = useState("");
    const [credentialProvider, setCredentialProvider] = useState("");
    const [credentialToken, setCredentialToken] = useState("");
    const [credentialTokenVisible, setCredentialTokenVisible] = useState(false);
    const [credentialModalBusy, setCredentialModalBusy] = useState(false);
    const [credentialModalError, setCredentialModalError] = useState<
        string | null
    >(null);
    const [confirmingCredentialId, setConfirmingCredentialId] = useState<
        string | null
    >(null);
    const [memberBusyId, setMemberBusyId] = useState<string | null>(null);
    const [confirmingMemberId, setConfirmingMemberId] = useState<string | null>(
        null,
    );
    const [isAddMemberModalOpen, setIsAddMemberModalOpen] = useState(false);
    const [memberModalError, setMemberModalError] = useState<string | null>(
        null,
    );
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const createWorkspaceButtonRef = useRef<HTMLButtonElement>(null);
    const createWorkspaceDialogRef = useRef<HTMLDivElement>(null);
    const addMemberDialogRef = useRef<HTMLDivElement>(null);
    const addMemberTriggerRef = useRef<HTMLButtonElement>(null);
    const credentialDialogRef = useRef<HTMLDivElement>(null);
    const credentialSecretRef = useRef<HTMLInputElement>(null);
    const credentialTriggerRef = useRef<HTMLButtonElement>(null);

    const selectedWorkspace = workspaces.find(
        (workspace) => workspace.id === selectedId,
    );
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
        const body = (await response.json()) as { data: Workspace[] };
        const saved = window.localStorage.getItem("vf-workspace-id");
        const id = body.data.some((workspace) => workspace.id === saved)
            ? saved
            : (body.data[0]?.id ?? null);
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
        const response = await apiFetch(
            `/v1/workspaces/${workspaceId}/members`,
        );
        if (!response.ok) {
            setError(await readApiError(response));
            setMemberLoading(false);
            return;
        }
        const body = (await response.json()) as { data: WorkspaceMember[] };
        setMembers(body.data);
        setMemberLoading(false);
    }

    async function loadCredentials(workspaceId: string) {
        setCredentialLoading(true);
        try {
            const nextCredentials = await fetchCredentials(workspaceId);
            setCredentials(
                nextCredentials.filter(
                    (credential) => credential.status === "ACTIVE",
                ),
            );
        } catch (loadError) {
            setError(
                loadError instanceof Error
                    ? loadError.message
                    : "Unable to load credentials.",
            );
        } finally {
            setCredentialLoading(false);
        }
    }

    useEffect(() => {
        void load();
    }, []);

    useEffect(() => {
        if (selectedId) void loadMembers(selectedId);
        else setMembers([]);
    }, [selectedId]);

    useEffect(() => {
        if (selectedId) void loadCredentials(selectedId);
        else setCredentials([]);
    }, [selectedId]);

    useEffect(() => {
        if (!isCreateModalOpen) return;
        const previousOverflow = document.body.style.overflow;
        const trigger = createWorkspaceButtonRef.current;
        document.body.style.overflow = "hidden";
        return () => {
            document.body.style.overflow = previousOverflow;
            trigger?.focus();
        };
    }, [isCreateModalOpen]);

    useEffect(() => {
        if (!isAddMemberModalOpen) return;
        const previousOverflow = document.body.style.overflow;
        const trigger = addMemberTriggerRef.current;
        document.body.style.overflow = "hidden";
        return () => {
            document.body.style.overflow = previousOverflow;
            trigger?.focus();
        };
    }, [isAddMemberModalOpen]);

    function handleAddMemberModalKeyDown(
        event: ReactKeyboardEvent<HTMLDivElement>,
    ) {
        if (event.key === "Escape" && memberBusyId !== "add-member") {
            setIsAddMemberModalOpen(false);
            return;
        }
        if (event.key !== "Tab") return;
        const focusable =
            addMemberDialogRef.current?.querySelectorAll<HTMLElement>(
                "button:not(:disabled), input:not(:disabled)",
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

    function handleCreateModalKeyDown(
        event: ReactKeyboardEvent<HTMLDivElement>,
    ) {
        if (event.key === "Escape") {
            setIsCreateModalOpen(false);
            return;
        }
        if (event.key !== "Tab") return;
        const focusable =
            createWorkspaceDialogRef.current?.querySelectorAll<HTMLElement>(
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

    useEffect(() => {
        if (!credentialModal) return;
        const previousOverflow = document.body.style.overflow;
        const trigger = credentialTriggerRef.current;
        document.body.style.overflow = "hidden";
        return () => {
            document.body.style.overflow = previousOverflow;
            trigger?.focus();
        };
    }, [credentialModal]);

    function handleCredentialModalKeyDown(
        event: ReactKeyboardEvent<HTMLDivElement>,
    ) {
        if (event.key === "Escape" && !credentialModalBusy) {
            closeCredentialModal();
            return;
        }
        if (event.key !== "Tab") return;
        const focusable =
            credentialDialogRef.current?.querySelectorAll<HTMLElement>(
                "button, input, select",
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

    function closeCredentialModal(force = false) {
        if (credentialModalBusy && !force) return;
        setCredentialModal(null);
        setCredentialModalId(null);
        setCredentialToken("");
        setCredentialTokenVisible(false);
        setCredentialModalError(null);
    }

    function openCreateCredential() {
        setCredentialModal("create");
        setCredentialModalId(null);
        setCredentialName("");
        setCredentialProvider("");
        setCredentialToken("");
        setCredentialTokenVisible(false);
        setCredentialModalError(null);
    }

    function openRotateCredential(credential: Credential) {
        setCredentialModal("rotate");
        setCredentialModalId(credential.id);
        setCredentialName(credential.name);
        setCredentialProvider(credential.provider);
        setCredentialToken("");
        setCredentialTokenVisible(false);
        setCredentialModalError(null);
    }

    async function submitCredential(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setCredentialModalError(null);
        if (!credentialToken.trim()) {
            setCredentialModalError(
                "Enter a token before saving the credential.",
            );
            credentialSecretRef.current?.focus();
            return;
        }
        if (
            credentialModal === "create" &&
            (!credentialName.trim() || !credentialProvider.trim())
        ) {
            setCredentialModalError(
                "Enter a name and provider before saving the credential.",
            );
            return;
        }
        if (!selectedId) return;
        setCredentialModalBusy(true);
        try {
            if (credentialModal === "create") {
                await createCredential(selectedId, {
                    name: credentialName.trim(),
                    provider: credentialProvider.trim(),
                    type: "API_KEY",
                    secret: { token: credentialToken },
                });
                setMessage("Credential encrypted and saved.");
            } else if (credentialModalId) {
                await rotateCredential(credentialModalId, credentialToken);
                setMessage(
                    "Credential rotated. The previous token is no longer active.",
                );
            }
            closeCredentialModal(true);
            await loadCredentials(selectedId);
        } catch (saveError) {
            setCredentialModalError(
                saveError instanceof Error
                    ? saveError.message
                    : "Unable to save credential.",
            );
        } finally {
            setCredentialToken("");
            setCredentialTokenVisible(false);
            setCredentialModalBusy(false);
        }
    }

    async function revokeWorkspaceCredential(credential: Credential) {
        if (!isOwner) return;
        setCredentialBusyId(credential.id);
        setError(null);
        try {
            await revokeCredential(credential.id);
            setCredentials((current) =>
                current.filter((item) => item.id !== credential.id),
            );
            setConfirmingCredentialId(null);
            setMessage(`${credential.name} was revoked.`);
        } catch (revokeError) {
            setError(
                revokeError instanceof Error
                    ? revokeError.message
                    : "Unable to revoke credential.",
            );
        } finally {
            setCredentialBusyId(null);
        }
    }

    async function createWorkspace(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError(null);
        setMessage(null);
        setMemberBusyId("create-workspace");
        const response = await apiFetch("/v1/workspaces", {
            method: "POST",
            body: JSON.stringify({
                name: newWorkspaceName,
                slug: newWorkspaceSlug,
            }),
        });
        if (!response.ok) {
            setError(await readApiError(response));
            setMemberBusyId(null);
            return;
        }
        const workspace = (await response.json()) as Workspace;
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

    function handleSettingsTabKeyDown(
        event: ReactKeyboardEvent<HTMLButtonElement>,
        currentTab: SettingsTab,
    ) {
        const tabButtons = Array.from(
            event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
                '[role="tab"]:not(:disabled)',
            ) ?? [],
        );
        const currentIndex = tabButtons.findIndex(
            (button) => button.dataset.settingsTab === currentTab,
        );
        let nextIndex = currentIndex;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") {
            nextIndex = (currentIndex + 1) % tabButtons.length;
        } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
            nextIndex = (currentIndex - 1 + tabButtons.length) % tabButtons.length;
        } else if (event.key === "Home") {
            nextIndex = 0;
        } else if (event.key === "End") {
            nextIndex = tabButtons.length - 1;
        } else {
            return;
        }
        event.preventDefault();
        const nextButton = tabButtons[nextIndex];
        const nextTab = nextButton?.dataset.settingsTab as SettingsTab | undefined;
        nextButton?.focus();
        if (nextTab) setActiveTab(nextTab);
    }

    async function addMember(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!selectedId || !isOwner) return;
        setMemberModalError(null);
        setMessage(null);
        setMemberBusyId("add-member");
        const response = await apiFetch(
            `/v1/workspaces/${selectedId}/members`,
            {
                method: "POST",
                body: JSON.stringify({ email: memberEmail }),
            },
        );
        if (!response.ok) {
            setMemberModalError(await readApiError(response));
            setMemberBusyId(null);
            return;
        }
        const member = (await response.json()) as WorkspaceMember;
        setMembers((current) => [...current, member]);
        setMemberEmail("");
        setIsAddMemberModalOpen(false);
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
        setMembers((current) =>
            current.filter((item) => item.user_id !== member.user_id),
        );
        setConfirmingMemberId(null);
        setMessage(`${member.email} was removed from the workspace.`);
        setMemberBusyId(null);
    }

    function selectProvider(value: ModelProviderId) {
        setProvider(value);
        setModelTestResult(null);
        setModelTestError(null);
        if (value === "azure_openai") {
            setModelName("gpt-6-luna");
            setDeploymentName("gpt-6-luna");
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
                deployment_name:
                    provider === "azure_openai" ? deploymentName : undefined,
                base_url:
                    provider === "azure_openai" && baseUrl.trim()
                        ? baseUrl.trim()
                        : undefined,
                api_key: apiKey,
            });
            setModelTestResult(result);
        } catch (testError) {
            setModelTestError(
                testError instanceof Error
                    ? testError.message
                    : "Connection test failed.",
            );
        } finally {
            setApiKey("");
            setModelTestBusy(false);
        }
    }

    return (
        <AppShell>
            <div className="page-header settings-page-header">
                <div>
                    <p className="eyebrow">VibesFactory / Workspace</p>
                    <h1>Settings</h1>
                    <p className="page-description">
                        Manage workspace identity, team access, model testing,
                        and encrypted credentials.
                    </p>
                </div>
                {activeTab === "workspace" ? (
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
                ) : null}
            </div>

            {error ? (
                <p className="form-error" role="alert">
                    {error}
                </p>
            ) : null}
            {message ? (
                <p className="form-success" role="status">
                    <Check size={14} aria-hidden="true" />
                    {message}
                </p>
            ) : null}

            <div className="settings-layout">
                <div
                    className="settings-tabs"
                    role="tablist"
                    aria-label="Workspace settings"
                    aria-orientation="vertical"
                >
                    {settingsTabs.map((tab) => {
                        const TabIcon = tab.icon;
                        return (
                            <button
                                id={`settings-tab-${tab.id}`}
                                data-settings-tab={tab.id}
                                className={`settings-tab${activeTab === tab.id ? " active" : ""}`}
                                key={tab.id}
                                type="button"
                                role="tab"
                                aria-selected={activeTab === tab.id}
                                aria-controls={`settings-panel-${tab.id}`}
                                tabIndex={activeTab === tab.id ? 0 : -1}
                                disabled={tab.id !== "workspace" && !selectedId}
                                onClick={() => setActiveTab(tab.id)}
                                onKeyDown={(event) =>
                                    handleSettingsTabKeyDown(event, tab.id)
                                }
                            >
                                <span className="settings-tab-icon">
                                    <TabIcon size={16} aria-hidden="true" />
                                </span>
                                <span className="settings-tab-copy">
                                    <strong>{tab.label}</strong>
                                    <small>{tab.description}</small>
                                </span>
                            </button>
                        );
                    })}
                </div>

                <div className="settings-content">
                    {loading ? (
                        <section
                            className="panel settings-content-state"
                            aria-live="polite"
                        >
                            <LoaderCircle
                                className="spin"
                                size={17}
                                aria-hidden="true"
                            />
                            Loading workspace settings…
                        </section>
                    ) : null}

            {!loading && activeTab === "workspace" ? (
                <section
                    id="settings-panel-workspace"
                    className="panel settings-section-panel workspace-settings-panel"
                    role="tabpanel"
                    aria-labelledby="settings-tab-workspace"
                    tabIndex={0}
                >
                    <div className="settings-section-heading">
                        <span className="settings-section-icon">
                            <Building2 size={18} aria-hidden="true" />
                        </span>
                        <div className="settings-section-copy">
                            <span className="panel-kicker">Workspace profile</span>
                            <h2>{selectedWorkspace?.name ?? "Create your first workspace"}</h2>
                            <p className="panel-copy">
                                Update the name used across your workspace. The slug remains fixed after creation.
                            </p>
                        </div>
                        {selectedWorkspace ? (
                            <span className="member-role owner">
                                <ShieldCheck size={13} aria-hidden="true" />
                                {selectedWorkspace.role === "OWNER" ? "Owner" : "Member"}
                            </span>
                        ) : null}
                    </div>
                    {selectedId ? (
                        <form
                            className="settings-form workspace-settings-form"
                            onSubmit={updateWorkspace}
                        >
                            <label htmlFor="workspace-name">Workspace name</label>
                            <PrimaryTextInput
                                id="workspace-name"
                                value={name}
                                onChange={(event) => setName(event.target.value)}
                                required
                                maxLength={255}
                            />
                            <div className="settings-readonly-field">
                                <span>Workspace slug</span>
                                <code>{slug}</code>
                                <small>Used in URLs and workspace-scoped resources.</small>
                            </div>
                            {isOwner ? (
                                <button
                                    className="button primary-button settings-save-button"
                                    type="submit"
                                    disabled={memberBusyId === "update-workspace"}
                                >
                                    {memberBusyId === "update-workspace" ? (
                                        <LoaderCircle className="spin" size={15} aria-hidden="true" />
                                    ) : null}
                                    Save workspace
                                </button>
                            ) : (
                                <div className="member-readonly-note">
                                    <ShieldCheck size={16} aria-hidden="true" />
                                    Only the workspace owner can change workspace details.
                                </div>
                            )}
                        </form>
                    ) : (
                        <div className="settings-empty-state">
                            <p className="panel-copy">
                                Create a workspace to isolate agents, credentials, and other platform resources.
                            </p>
                        </div>
                    )}
                </section>
            ) : null}

            {!loading && activeTab === "members" && selectedId ? (
                <section
                    id="settings-panel-members"
                    className="panel settings-section-panel members-panel"
                    role="tabpanel"
                    aria-labelledby="settings-tab-members"
                    tabIndex={0}
                >
                    <div className="settings-section-heading">
                        <span className="settings-section-icon">
                            <UsersRound size={18} aria-hidden="true" />
                        </span>
                        <div className="settings-section-copy">
                            <span className="panel-kicker">
                                Workspace access
                            </span>
                            <h2>Members</h2>
                            <p className="panel-copy">
                                Control who can access{" "}
                                {selectedWorkspace?.name ?? "this workspace"}.
                            </p>
                        </div>
                        <div className="member-heading-actions">
                            <span className="status-badge info">
                                <span />
                                {members.length}{" "}
                                {members.length === 1 ? "member" : "members"}
                            </span>
                            {isOwner ? (
                                <button
                                    ref={addMemberTriggerRef}
                                    className="button primary-button"
                                    type="button"
                                    onClick={() => {
                                        setMemberEmail("");
                                        setMemberModalError(null);
                                        setIsAddMemberModalOpen(true);
                                    }}
                                >
                                    <Plus size={15} aria-hidden="true" />
                                    Add member
                                </button>
                            ) : null}
                        </div>
                    </div>

                    <div className="member-list" aria-live="polite">
                        {memberLoading ? (
                            <div className="member-list-state">
                                Loading members…
                            </div>
                        ) : null}
                        {!memberLoading && members.length === 0 ? (
                            <div className="member-list-state member-empty-state">
                                <UsersRound size={25} aria-hidden="true" />
                                <strong>No members yet</strong>
                                <span>
                                    {isOwner
                                        ? "Add an existing VibesFactory user to start collaborating."
                                        : "Workspace members will appear here."}
                                </span>
                            </div>
                        ) : null}
                        {!memberLoading &&
                            members.map((member) => (
                                <div
                                    className="member-row"
                                    key={member.user_id}
                                >
                                    <div
                                        className="member-avatar"
                                        aria-hidden="true"
                                    >
                                        {initials(member.email)}
                                    </div>
                                    <div className="member-copy">
                                        <strong>{member.email}</strong>
                                        <span>
                                            Joined{" "}
                                            {joinedDate(member.created_at)}
                                        </span>
                                    </div>
                                    <span
                                        className={`member-role ${member.role.toLowerCase()}`}
                                    >
                                        {member.role === "OWNER" ? (
                                            <ShieldCheck
                                                size={13}
                                                aria-hidden="true"
                                            />
                                        ) : null}
                                        {member.role === "OWNER"
                                            ? "Owner"
                                            : "Member"}
                                    </span>
                                    {member.role === "OWNER" || !isOwner ? (
                                        <span
                                            className="member-action-placeholder"
                                            aria-hidden="true"
                                        />
                                    ) : confirmingMemberId ===
                                      member.user_id ? (
                                        <div className="member-confirm-actions">
                                            <button
                                                className="text-button"
                                                type="button"
                                                onClick={() =>
                                                    setConfirmingMemberId(null)
                                                }
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                className="button danger-button"
                                                type="button"
                                                disabled={
                                                    memberBusyId ===
                                                    member.user_id
                                                }
                                                onClick={() =>
                                                    void removeMember(member)
                                                }
                                            >
                                                {memberBusyId ===
                                                member.user_id ? (
                                                    <LoaderCircle
                                                        className="spin"
                                                        size={13}
                                                        aria-hidden="true"
                                                    />
                                                ) : null}
                                                Remove
                                            </button>
                                        </div>
                                    ) : (
                                        <button
                                            className="icon-button danger-icon"
                                            type="button"
                                            aria-label={`Remove ${member.email}`}
                                            onClick={() =>
                                                setConfirmingMemberId(
                                                    member.user_id,
                                                )
                                            }
                                        >
                                            <UserMinus
                                                size={16}
                                                aria-hidden="true"
                                            />
                                        </button>
                                    )}
                                </div>
                            ))}
                    </div>
                </section>
            ) : null}

            {!loading && activeTab === "model-test" && selectedId ? (
                <section
                    id="settings-panel-model-test"
                    className="panel settings-section-panel model-test-panel"
                    role="tabpanel"
                    aria-labelledby="settings-tab-model-test"
                    tabIndex={0}
                >
                    <div className="settings-section-heading">
                        <span className="settings-section-icon">
                            <Cloud size={18} aria-hidden="true" />
                        </span>
                        <div className="settings-section-copy">
                            <span className="panel-kicker">
                                Ephemeral provider probe
                            </span>
                            <h2>Test Model Connection</h2>
                            <p className="panel-copy">
                                Verify a provider key with one low-token
                                request. The key is cleared from this form after
                                the test.
                            </p>
                        </div>
                        <span className="status-badge info">
                            <span />
                            Ephemeral key only
                        </span>
                    </div>

                    <form
                        className="model-test-form"
                        onSubmit={submitModelTest}
                    >
                        <div className="model-test-field-grid">
                            <label htmlFor="model-test-provider-trigger">
                                Provider
                                <PrimarySelect
                                    id="model-test-provider-trigger"
                                    value={provider}
                                    options={modelProviderOptions}
                                    placeholder="Choose provider"
                                    ariaLabel="Provider"
                                    onChange={(value) =>
                                        selectProvider(value as ModelProviderId)
                                    }
                                />
                            </label>
                            <label htmlFor="model-test-model">
                                Model / deployment ID
                                <PrimaryTextInput
                                    id="model-test-model"
                                    value={modelName}
                                    onChange={(event) =>
                                        setModelName(event.target.value)
                                    }
                                    placeholder="gpt-4.1-mini"
                                    required
                                />
                            </label>
                            {provider === "azure_openai" ? (
                                <label htmlFor="model-test-deployment">
                                    Azure deployment name
                                    <PrimaryTextInput
                                        id="model-test-deployment"
                                        value={deploymentName}
                                        onChange={(event) =>
                                            setDeploymentName(
                                                event.target.value,
                                            )
                                        }
                                        placeholder="gpt-6-luna"
                                        required
                                    />
                                </label>
                            ) : null}
                            {provider === "azure_openai" ? (
                                <label
                                    className="model-test-wide"
                                    htmlFor="model-test-base-url"
                                >
                                    Azure base URL
                                    <PrimaryTextInput
                                        id="model-test-base-url"
                                        type="url"
                                        value={baseUrl}
                                        onChange={(event) =>
                                            setBaseUrl(event.target.value)
                                        }
                                        placeholder="https://resource.services.ai.azure.com/openai/v1"
                                        required
                                    />
                                </label>
                            ) : null}
                            <label
                                className="model-test-wide"
                                htmlFor="model-test-api-key"
                            >
                                API key
                                <PrimaryTextInput
                                    id="model-test-api-key"
                                    type="password"
                                    autoComplete="new-password"
                                    value={apiKey}
                                    onChange={(event) =>
                                        setApiKey(event.target.value)
                                    }
                                    placeholder="Enter a temporary provider key"
                                    required
                                />
                            </label>
                        </div>
                        <div className="model-test-actions">
                            <p className="field-helper">
                                <Cloud size={13} aria-hidden="true" /> Sent only
                                to the selected provider through the
                                authenticated API.
                            </p>
                            <button
                                className="button primary-button"
                                type="submit"
                                disabled={modelTestBusy || !apiKey.trim()}
                            >
                                {modelTestBusy ? (
                                    <LoaderCircle
                                        className="spin"
                                        size={15}
                                        aria-hidden="true"
                                    />
                                ) : (
                                    <KeyRound size={15} aria-hidden="true" />
                                )}
                                {modelTestBusy ? "Testing…" : "Test connection"}
                            </button>
                        </div>
                    </form>

                    {modelTestError ? (
                        <div className="model-test-result failed" role="alert">
                            <X size={16} aria-hidden="true" />
                            <div>
                                <strong>Request failed</strong>
                                <span>{modelTestError}</span>
                            </div>
                        </div>
                    ) : null}
                    {modelTestResult?.status === "SUCCESS" ? (
                        <div
                            className="model-test-result success"
                            role="status"
                        >
                            <Check size={16} aria-hidden="true" />
                            <div>
                                <strong>Connection successful</strong>
                                <span>
                                    {modelTestResult.provider} ·{" "}
                                    {modelTestResult.model_name} ·{" "}
                                    {modelTestResult.latency_ms ?? 0} ms
                                </span>
                            </div>
                        </div>
                    ) : null}
                    {modelTestResult?.status === "FAILED" &&
                    modelTestResult.error ? (
                        <div className="model-test-result failed" role="alert">
                            <X size={16} aria-hidden="true" />
                            <div>
                                <strong>Connection failed</strong>
                                <span>{modelTestResult.error.message}</span>
                                <small>{modelTestResult.error.code}</small>
                            </div>
                        </div>
                    ) : null}
                </section>
            ) : null}

            {!loading && activeTab === "credentials" && selectedId ? (
                <section
                    id="settings-panel-credentials"
                    className="panel settings-section-panel credentials-panel"
                    role="tabpanel"
                    aria-labelledby="settings-tab-credentials"
                    tabIndex={0}
                >
                    <div className="settings-section-heading">
                        <span className="settings-section-icon">
                            <LockKeyhole size={18} aria-hidden="true" />
                        </span>
                        <div className="settings-section-copy">
                            <span className="panel-kicker">
                                Encrypted workspace vault
                            </span>
                            <h2>Credentials</h2>
                            <p className="panel-copy">
                                Store API tokens separately from agents and
                                tools. Secret values are never shown again after
                                submission.
                            </p>
                        </div>
                        <div className="credentials-heading-actions">
                            <span className="status-badge success">
                                <span />
                                AES-GCM encrypted
                            </span>
                            {isOwner ? (
                                <button
                                    ref={credentialTriggerRef}
                                    className="button primary-button"
                                    type="button"
                                    onClick={openCreateCredential}
                                >
                                    <Plus size={15} aria-hidden="true" />
                                    Add credential
                                </button>
                            ) : null}
                        </div>
                    </div>

                    {!isOwner ? (
                        <div className="member-readonly-note">
                            <ShieldCheck size={16} aria-hidden="true" />
                            You can view credential metadata, but only the
                            workspace owner can add, rotate, or revoke secrets.
                        </div>
                    ) : null}
                    <div className="credentials-list" aria-live="polite">
                        {credentialLoading ? (
                            <div className="member-list-state">
                                <LoaderCircle
                                    className="spin"
                                    size={16}
                                    aria-hidden="true"
                                />
                                Loading credentials…
                            </div>
                        ) : null}
                        {!credentialLoading && credentials.length === 0 ? (
                            <div className="member-list-state member-empty-state">
                                <LockKeyhole size={25} aria-hidden="true" />
                                <strong>No credentials yet</strong>
                                <span>
                                    Add an API token to use it from an HTTP tool
                                    without exposing it to the model.
                                </span>
                            </div>
                        ) : null}
                        {!credentialLoading &&
                            credentials.map((credential) => (
                                <div
                                    className="credential-row"
                                    key={credential.id}
                                >
                                    <div
                                        className="credential-icon"
                                        aria-hidden="true"
                                    >
                                        <KeyRound size={16} />
                                    </div>
                                    <div className="credential-copy">
                                        <strong>{credential.name}</strong>
                                        <span>
                                            {credential.provider} ·{" "}
                                            {credential.type} · Added{" "}
                                            {joinedDate(credential.created_at)}
                                        </span>
                                    </div>
                                    <span
                                        className={`status-badge ${credential.status === "ACTIVE" ? "success" : "muted"}`}
                                    >
                                        <span />
                                        {credential.status === "ACTIVE"
                                            ? "Active"
                                            : "Revoked"}
                                    </span>
                                    {isOwner &&
                                    credential.status === "ACTIVE" ? (
                                        confirmingCredentialId ===
                                        credential.id ? (
                                            <div className="member-confirm-actions">
                                                <button
                                                    className="text-button"
                                                    type="button"
                                                    onClick={() =>
                                                        setConfirmingCredentialId(
                                                            null,
                                                        )
                                                    }
                                                >
                                                    Cancel
                                                </button>
                                                <button
                                                    className="button danger-button"
                                                    type="button"
                                                    disabled={
                                                        credentialBusyId ===
                                                        credential.id
                                                    }
                                                    onClick={() =>
                                                        void revokeWorkspaceCredential(
                                                            credential,
                                                        )
                                                    }
                                                >
                                                    {credentialBusyId ===
                                                    credential.id ? (
                                                        <LoaderCircle
                                                            className="spin"
                                                            size={13}
                                                            aria-hidden="true"
                                                        />
                                                    ) : null}
                                                    Revoke
                                                </button>
                                            </div>
                                        ) : (
                                            <div className="credential-actions">
                                                <button
                                                    className="icon-button"
                                                    type="button"
                                                    aria-label={`Rotate ${credential.name}`}
                                                    onClick={() =>
                                                        openRotateCredential(
                                                            credential,
                                                        )
                                                    }
                                                >
                                                    <RotateCcw
                                                        size={15}
                                                        aria-hidden="true"
                                                    />
                                                </button>
                                                <button
                                                    className="icon-button danger-icon"
                                                    type="button"
                                                    aria-label={`Revoke ${credential.name}`}
                                                    onClick={() =>
                                                        setConfirmingCredentialId(
                                                            credential.id,
                                                        )
                                                    }
                                                >
                                                    <Trash2
                                                        size={15}
                                                        aria-hidden="true"
                                                    />
                                                </button>
                                            </div>
                                        )
                                    ) : null}
                                </div>
                            ))}
                    </div>
                </section>
            ) : null}

                </div>
            </div>

            {isCreateModalOpen ? (
                <div
                    className="modal-backdrop"
                    role="presentation"
                    onMouseDown={(event) => {
                        if (event.target === event.currentTarget)
                            setIsCreateModalOpen(false);
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
                                <span className="panel-kicker">
                                    New tenant boundary
                                </span>
                                <h2 id="create-workspace-title">
                                    Create workspace
                                </h2>
                                <p className="panel-copy">
                                    Give your new workspace a clear identity to
                                    keep agents and resources isolated.
                                </p>
                            </div>
                            <button
                                className="icon-button modal-close"
                                type="button"
                                aria-label="Close create workspace dialog"
                                onClick={() => setIsCreateModalOpen(false)}
                            >
                                <X size={17} aria-hidden="true" />
                            </button>
                        </div>
                        <form
                            className="settings-form modal-form"
                            onSubmit={createWorkspace}
                        >
                            <label htmlFor="new-workspace-name">Name</label>
                            <PrimaryTextInput
                                id="new-workspace-name"
                                value={newWorkspaceName}
                                onChange={(event) =>
                                    setNewWorkspaceName(event.target.value)
                                }
                                placeholder="Personal AI Lab"
                                required
                            />
                            <label htmlFor="new-workspace-slug">Slug</label>
                            <PrimaryTextInput
                                id="new-workspace-slug"
                                value={newWorkspaceSlug}
                                onChange={(event) =>
                                    setNewWorkspaceSlug(event.target.value)
                                }
                                placeholder="personal-ai-lab"
                                pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
                                required
                            />
                            <p className="field-helper">
                                Use lowercase letters, numbers, and hyphens.
                            </p>
                            <div className="modal-actions">
                                <button
                                    className="button secondary-button"
                                    type="button"
                                    onClick={() => setIsCreateModalOpen(false)}
                                >
                                    Cancel
                                </button>
                                <button
                                    className="button primary-button"
                                    type="submit"
                                    disabled={
                                        memberBusyId === "create-workspace"
                                    }
                                >
                                    {memberBusyId === "create-workspace" ? (
                                        <LoaderCircle
                                            className="spin"
                                            size={15}
                                            aria-hidden="true"
                                        />
                                    ) : (
                                        <Plus size={15} aria-hidden="true" />
                                    )}
                                    Create workspace
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            ) : null}

            {isAddMemberModalOpen ? (
                <div
                    className="modal-backdrop"
                    role="presentation"
                    onMouseDown={(event) => {
                        if (
                            event.target === event.currentTarget &&
                            memberBusyId !== "add-member"
                        ) {
                            setIsAddMemberModalOpen(false);
                        }
                    }}
                >
                    <div
                        ref={addMemberDialogRef}
                        className="modal-dialog"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="add-member-title"
                        aria-describedby="add-member-description"
                        onKeyDown={handleAddMemberModalKeyDown}
                    >
                        <div className="modal-heading">
                            <div>
                                <span className="panel-kicker">
                                    Workspace access
                                </span>
                                <h2 id="add-member-title">Add member</h2>
                                <p
                                    id="add-member-description"
                                    className="panel-copy"
                                >
                                    Enter the email address of a user who has
                                    signed in to VibesFactory at least once.
                                </p>
                            </div>
                            <button
                                className="icon-button modal-close"
                                type="button"
                                aria-label="Close add member dialog"
                                disabled={memberBusyId === "add-member"}
                                onClick={() => setIsAddMemberModalOpen(false)}
                            >
                                <X size={17} aria-hidden="true" />
                            </button>
                        </div>
                        <form
                            className="settings-form modal-form"
                            onSubmit={addMember}
                        >
                            <label htmlFor="member-email">Member email</label>
                            <PrimaryTextInput
                                id="member-email"
                                type="email"
                                autoComplete="email"
                                value={memberEmail}
                                onChange={(event) =>
                                    setMemberEmail(event.target.value)
                                }
                                placeholder="teammate@company.com"
                                required
                            />
                            {memberModalError ? (
                                <p className="form-error" role="alert">
                                    {memberModalError}
                                </p>
                            ) : null}
                            <div className="modal-actions">
                                <button
                                    className="button secondary-button"
                                    type="button"
                                    disabled={memberBusyId === "add-member"}
                                    onClick={() =>
                                        setIsAddMemberModalOpen(false)
                                    }
                                >
                                    Cancel
                                </button>
                                <button
                                    className="button primary-button"
                                    type="submit"
                                    disabled={
                                        memberBusyId === "add-member" ||
                                        !memberEmail.trim()
                                    }
                                >
                                    {memberBusyId === "add-member" ? (
                                        <LoaderCircle
                                            className="spin"
                                            size={15}
                                            aria-hidden="true"
                                        />
                                    ) : (
                                        <Plus size={15} aria-hidden="true" />
                                    )}
                                    {memberBusyId === "add-member"
                                        ? "Adding member…"
                                        : "Add member"}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            ) : null}

            {credentialModal ? (
                <div
                    className="modal-backdrop"
                    role="presentation"
                    onMouseDown={(event) => {
                        if (
                            event.target === event.currentTarget &&
                            !credentialModalBusy
                        )
                            closeCredentialModal();
                    }}
                >
                    <div
                        ref={credentialDialogRef}
                        className="modal-dialog credential-modal"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="credential-modal-title"
                        onKeyDown={handleCredentialModalKeyDown}
                    >
                        <div className="modal-heading">
                            <div>
                                <span className="panel-kicker">
                                    {credentialModal === "create"
                                        ? "New vault entry"
                                        : "Secret rotation"}
                                </span>
                                <h2 id="credential-modal-title">
                                    {credentialModal === "create"
                                        ? "Add credential"
                                        : `Rotate ${credentialName}`}
                                </h2>
                                <p className="panel-copy">
                                    {credentialModal === "create"
                                        ? "Save an API token for workspace tools. The token is encrypted before it reaches the database."
                                        : "Enter a new token. The previous value will become inaccessible after rotation."}
                                </p>
                            </div>
                            <button
                                className="icon-button modal-close"
                                type="button"
                                aria-label="Close credential dialog"
                                disabled={credentialModalBusy}
                                onClick={() => closeCredentialModal()}
                            >
                                <X size={17} aria-hidden="true" />
                            </button>
                        </div>
                        <form
                            className="settings-form modal-form"
                            onSubmit={submitCredential}
                        >
                            {credentialModal === "create" ? (
                                <>
                                    <label htmlFor="credential-name">
                                        Name
                                        <PrimaryTextInput
                                            id="credential-name"
                                            value={credentialName}
                                            onChange={(event) =>
                                                setCredentialName(
                                                    event.target.value,
                                                )
                                            }
                                            placeholder="GitHub API"
                                            required
                                        />
                                    </label>
                                    <label htmlFor="credential-provider">
                                        Provider
                                        <PrimaryTextInput
                                            id="credential-provider"
                                            value={credentialProvider}
                                            onChange={(event) =>
                                                setCredentialProvider(
                                                    event.target.value,
                                                )
                                            }
                                            placeholder="github"
                                            required
                                        />
                                    </label>
                                </>
                            ) : (
                                <div className="credential-rotation-meta">
                                    <span>Provider</span>
                                    <strong>{credentialProvider}</strong>
                                    <span>Type</span>
                                    <strong>API_KEY</strong>
                                </div>
                            )}
                            <label htmlFor="credential-token">
                                API token
                                <PrimaryTextInput
                                    ref={credentialSecretRef}
                                    id="credential-token"
                                    type={
                                        credentialTokenVisible
                                            ? "text"
                                            : "password"
                                    }
                                    autoComplete="new-password"
                                    value={credentialToken}
                                    onChange={(event) =>
                                        setCredentialToken(event.target.value)
                                    }
                                    placeholder="Paste token value"
                                    required
                                    aria-describedby="credential-token-help"
                                />
                                <button
                                    className="credential-token-toggle"
                                    type="button"
                                    aria-label={
                                        credentialTokenVisible
                                            ? "Hide API token"
                                            : "Show API token"
                                    }
                                    onClick={() =>
                                        setCredentialTokenVisible(
                                            (visible) => !visible,
                                        )
                                    }
                                >
                                    {credentialTokenVisible ? (
                                        <EyeOff size={15} aria-hidden="true" />
                                    ) : (
                                        <Eye size={15} aria-hidden="true" />
                                    )}
                                </button>
                            </label>
                            <p
                                id="credential-token-help"
                                className="field-helper"
                            >
                                <LockKeyhole size={13} aria-hidden="true" /> The
                                token is write-only in VibesFactory and is never
                                returned by the API.
                            </p>
                            {credentialModalError ? (
                                <p className="form-error" role="alert">
                                    {credentialModalError}
                                </p>
                            ) : null}
                            <div className="modal-actions">
                                <button
                                    className="button secondary-button"
                                    type="button"
                                    disabled={credentialModalBusy}
                                    onClick={() => closeCredentialModal()}
                                >
                                    Cancel
                                </button>
                                <button
                                    className="button primary-button"
                                    type="submit"
                                    disabled={
                                        credentialModalBusy ||
                                        !credentialToken.trim()
                                    }
                                >
                                    {credentialModalBusy ? (
                                        <LoaderCircle
                                            className="spin"
                                            size={15}
                                            aria-hidden="true"
                                        />
                                    ) : (
                                        <LockKeyhole
                                            size={15}
                                            aria-hidden="true"
                                        />
                                    )}
                                    {credentialModal === "create"
                                        ? "Save encrypted credential"
                                        : "Rotate credential"}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            ) : null}
        </AppShell>
    );
}
