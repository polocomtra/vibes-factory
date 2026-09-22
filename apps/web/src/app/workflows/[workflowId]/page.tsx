"use client";

import dynamic from "next/dynamic";
import { ArrowLeft, Check, History, LoaderCircle, Pencil, X } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "../../../components/app-shell";
import { FeedbackToast, type FeedbackToastState } from "../../../components/feedback-toast";
import {
    fetchAgents,
    fetchVersions,
    type Agent,
    type AgentVersionSummary,
} from "../../../lib/agents";
import { apiFetch, readApiError } from "../../../lib/api";
import { fetchTools, type Tool } from "../../../lib/tools";
import {
    fetchWorkflow,
    fetchWorkflowDraft,
    fetchWorkflowVersions,
    updateWorkflow,
    type Workflow,
    type WorkflowDraft,
} from "../../../lib/workflows";

const WorkflowEditor = dynamic(
    () =>
        import("../../../components/workflow-editor").then(
            (module) => module.WorkflowEditor,
        ),
    {
        ssr: false,
        loading: () => (
            <section className="panel agent-state">
                <LoaderCircle className="spin" size={18} />
                Loading canvas…
            </section>
        ),
    },
);

export default function WorkflowDetailPage() {
    const params = useParams<{ workflowId: string }>();
    const router = useRouter();
    const [workflow, setWorkflow] = useState<Workflow | null>(null);
    const [draft, setDraft] = useState<WorkflowDraft | null>(null);
    const [latestVersionId, setLatestVersionId] = useState<string | null>(null);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [agentVersions, setAgentVersions] = useState<AgentVersionSummary[]>(
        [],
    );
    const [tools, setTools] = useState<Tool[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [renaming, setRenaming] = useState(false);
    const [nameDraft, setNameDraft] = useState("");
    const [renameBusy, setRenameBusy] = useState(false);
    const [toast, setToast] = useState<FeedbackToastState | null>(null);

    function beginRename() {
        if (!workflow) return;
        setNameDraft(workflow.name);
        setRenaming(true);
        setToast(null);
    }

    function cancelRename() {
        if (renameBusy) return;
        setRenaming(false);
        setNameDraft(workflow?.name ?? "");
    }

    async function saveRename() {
        const name = nameDraft.trim();
        if (!workflow || !name) {
            setToast({ kind: "error", message: "Workflow name cannot be empty." });
            return;
        }
        if (name === workflow.name) {
            setRenaming(false);
            return;
        }
        setRenameBusy(true);
        setToast({ kind: "loading", message: "Renaming workflow…" });
        try {
            const updated = await updateWorkflow(workflow.id, { name });
            setWorkflow(updated);
            setRenaming(false);
            setToast({ kind: "success", message: "Workflow renamed." });
        } catch (reason: unknown) {
            setToast({ kind: "error", message: reason instanceof Error ? reason.message : "Unable to rename workflow." });
        } finally {
            setRenameBusy(false);
        }
    }

    useEffect(() => {
        let cancelled = false;
        async function load() {
            try {
                const [nextWorkflow, nextDraft, versions, workspaceResponse] =
                    await Promise.all([
                        fetchWorkflow(params.workflowId),
                        fetchWorkflowDraft(params.workflowId),
                        fetchWorkflowVersions(params.workflowId),
                        apiFetch("/v1/workspaces"),
                    ]);
                if (!cancelled) {
                    setWorkflow(nextWorkflow);
                    setDraft(nextDraft);
                    setLatestVersionId(versions[0]?.id ?? null);
                }
                if (!workspaceResponse.ok) return;
                const workspaceBody = (await workspaceResponse.json()) as {
                    data: Array<{ id: string }>;
                };
                const savedWorkspaceId =
                    window.localStorage.getItem("vf-workspace-id");
                const workspaceId =
                    workspaceBody.data.find(
                        (workspace) => workspace.id === savedWorkspaceId,
                    )?.id ?? workspaceBody.data[0]?.id;
                if (!workspaceId) throw new Error("No workspace is available.");
                const [nextAgents, nextTools] = await Promise.all([
                    fetchAgents(workspaceId),
                    fetchTools(workspaceId),
                ]);
                const nextAgentVersions = (
                    await Promise.all(
                        nextAgents.map((agent) => fetchVersions(agent.id)),
                    )
                ).flat();
                if (cancelled) return;
                setAgents(nextAgents);
                setAgentVersions(nextAgentVersions);
                setTools(nextTools);
            } catch (reason: unknown) {
                if (!cancelled)
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : "Unable to load workflow.",
                    );
            }
        }
        void load();
        return () => {
            cancelled = true;
        };
    }, [params.workflowId]);

    return (
        <AppShell>
            <div className="workflow-detail-page">
                <button
                    className="back-link"
                    type="button"
                    onClick={() => router.push("/workflows")}
                >
                    <ArrowLeft size={15} aria-hidden="true" />
                    Back to workflows
                </button>
                {error ? (
                    <div className="form-error agent-alert" role="alert">
                        {error}
                    </div>
                ) : null}
                {workflow && draft ? (
                    <>
                        <div className="page-header workflow-detail-header">
                            <div>
                                <div className="workflow-title-row">
                                    {renaming ? (
                                        <form className="workflow-rename-form" onSubmit={(event) => { event.preventDefault(); void saveRename(); }}>
                                            <label className="sr-only" htmlFor="workflow-name">Workflow name</label>
                                            <input id="workflow-name" value={nameDraft} onChange={(event) => setNameDraft(event.target.value)} autoFocus disabled={renameBusy} maxLength={255} />
                                            <button className="icon-button" type="submit" disabled={renameBusy} aria-label="Save workflow name"><Check size={16} aria-hidden="true" /></button>
                                            <button className="icon-button" type="button" onClick={cancelRename} disabled={renameBusy} aria-label="Cancel rename"><X size={16} aria-hidden="true" /></button>
                                        </form>
                                    ) : (
                                        <>
                                            <h1>{workflow.name}</h1>
                                            <button className="icon-button workflow-title-edit" type="button" onClick={beginRename} aria-label={`Rename ${workflow.name}`} title="Rename workflow">
                                                <Pencil size={16} aria-hidden="true" />
                                            </button>
                                        </>
                                    )}
                                </div>
                                <p className="page-description">
                                    {workflow.description ||
                                        "Design and observe a deterministic multi-agent workflow."}
                                </p>
                            </div>
                            <div className="workflow-detail-header-actions">
                                <button className="button subtle-button" type="button" onClick={() => router.push(`/workflows/${workflow.id}/runs`)}>
                                    <History size={15} aria-hidden="true" />Run history
                                </button>
                                <span className="status-badge success">
                                    <span />
                                    {workflow.latest_version_number
                                        ? `Published v${workflow.latest_version_number}`
                                        : "Draft"}
                                </span>
                            </div>
                        </div>
                        <FeedbackToast toast={toast} onDismiss={() => setToast(null)} />
                        <WorkflowEditor
                            workflowId={workflow.id}
                            initialDraft={draft}
                            latestVersionId={latestVersionId}
                            agents={agents}
                            agentVersions={agentVersions}
                            tools={tools}
                        />
                    </>
                ) : !error ? (
                    <section className="panel agent-state">
                        <LoaderCircle className="spin" size={18} />
                        Loading workflow…
                    </section>
                ) : null}
            </div>
        </AppShell>
    );
}
