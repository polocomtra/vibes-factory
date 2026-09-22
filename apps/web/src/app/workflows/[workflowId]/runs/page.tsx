"use client";

import {
    ArrowLeft,
    ArrowRight,
    CheckCircle2,
    CircleAlert,
    Clock3,
    GitBranch,
    History,
    LoaderCircle,
    StopCircle,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "../../../../components/app-shell";
import {
    fetchWorkflow,
    fetchWorkflowRuns,
    type Workflow,
    type WorkflowRunSummary,
} from "../../../../lib/workflows";

function statusIcon(status: WorkflowRunSummary["status"]) {
    if (status === "COMPLETED") return <CheckCircle2 size={16} />;
    if (status === "FAILED") return <CircleAlert size={16} />;
    if (status === "CANCELLED") return <StopCircle size={16} />;
    return <LoaderCircle size={16} className="spin" />;
}

function duration(run: WorkflowRunSummary) {
    if (!run.started_at) return "Not started";
    const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
    return `${Math.max(0, Math.round((end - new Date(run.started_at).getTime()) / 1000))}s`;
}

export default function WorkflowRunsPage() {
    const params = useParams<{ workflowId: string }>();
    const router = useRouter();
    const [workflow, setWorkflow] = useState<Workflow | null>(null);
    const [runs, setRuns] = useState<WorkflowRunSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        async function load() {
            try {
                const [nextWorkflow, nextRuns] = await Promise.all([
                    fetchWorkflow(params.workflowId),
                    fetchWorkflowRuns(params.workflowId),
                ]);
                if (cancelled) return;
                setWorkflow(nextWorkflow);
                setRuns(nextRuns.data);
            } catch (reason: unknown) {
                if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load workflow runs.");
            } finally {
                if (!cancelled) setLoading(false);
            }
        }
        void load();
        return () => {
            cancelled = true;
        };
    }, [params.workflowId]);

    return (
        <AppShell>
            <div className="workflow-detail-page workflow-history-page">
                <button className="back-link" type="button" onClick={() => router.push(`/workflows/${params.workflowId}`)}>
                    <ArrowLeft size={15} aria-hidden="true" />Back to workflow
                </button>
                <div className="page-header workflow-history-header">
                    <div>
                        <p className="eyebrow">VibesFactory / Operate / Workflow history</p>
                        <h1>{workflow?.name || "Run history"}</h1>
                        <p className="page-description">Review previous executions, outputs and terminal states for this workflow.</p>
                    </div>
                    <span className="status-badge info"><History size={13} aria-hidden="true" />{runs.length} runs</span>
                </div>

                {error ? <div className="form-error agent-alert" role="alert">{error}</div> : null}
                {loading ? <section className="panel agent-state"><LoaderCircle className="spin" size={18} />Loading run history…</section> : null}
                {!loading && !error && runs.length === 0 ? (
                    <section className="panel agent-empty-state workflow-history-empty">
                        <History size={30} aria-hidden="true" />
                        <h2>No runs yet</h2>
                        <p className="panel-copy">Run this workflow once and its execution history will appear here.</p>
                        <button className="button primary-button" type="button" onClick={() => router.push(`/workflows/${params.workflowId}`)}>Open workflow</button>
                    </section>
                ) : null}
                {!loading && runs.length > 0 ? (
                    <section className="workflow-history-list" aria-label="Workflow runs">
                        {runs.map((run) => (
                            <button key={run.id} type="button" className="workflow-history-row" onClick={() => router.push(`/workflow-runs/${run.id}`)}>
                                <span className={`workflow-history-status ${run.status.toLowerCase()}`} aria-hidden="true">{statusIcon(run.status)}</span>
                                <span className="workflow-history-main">
                                    <span className="workflow-history-title"><strong>{run.status}</strong><small>{new Date(run.created_at).toLocaleString()}</small></span>
                                    <span className="workflow-history-meta">
                                        <span><Clock3 size={13} aria-hidden="true" />{duration(run)}</span>
                                        <span><GitBranch size={13} aria-hidden="true" />Current: {run.current_node_name || "—"}</span>
                                        <span>Tokens {String(run.usage.total_tokens ?? "—")}</span>
                                    </span>
                                </span>
                                <ArrowRight size={17} aria-hidden="true" />
                            </button>
                        ))}
                    </section>
                ) : null}
            </div>
        </AppShell>
    );
}
