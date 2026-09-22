"use client";

import { ArrowLeft } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "../../../components/app-shell";
import { WorkflowRunView } from "../../../components/workflow-run-view";

export default function WorkflowRunPage() { const params = useParams<{ workflowRunId: string }>(); const router = useRouter(); return <AppShell><div className="workflow-detail-page workflow-run-page"><button className="back-link" type="button" onClick={() => router.push("/workflows")}><ArrowLeft size={15} />Back to workflows</button><div className="page-header"><div><p className="eyebrow">VibesFactory / Operate / Workflow run</p><h1>Workflow run</h1><p className="page-description">Durable event replay keeps this timeline useful across reloads and worker reconnects.</p></div></div><WorkflowRunView runId={params.workflowRunId} /></div></AppShell>; }
