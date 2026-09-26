import { apiFetch, readApiErrorDetails } from "./api";

export type Approval = {
  id: string;
  workspace_id: string;
  kind: "TOOL_CALL" | "WORKFLOW_NODE";
  run_id: string | null;
  workflow_run_id: string | null;
  workflow_node_run_id: string | null;
  tool_version_id: string | null;
  tool_call_id: string | null;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  requested_action: string;
  arguments: Record<string, unknown>;
  risk_reason: string;
  expires_at: string;
  requested_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
};

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw await readApiErrorDetails(response);
  return response.json() as Promise<T>;
}

export async function fetchApprovals(
  workspaceId: string,
  status?: Approval["status"],
  kind?: Approval["kind"],
  filters?: { runId?: string; workflowRunId?: string },
): Promise<Approval[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (kind) params.set("kind", kind);
  if (filters?.runId) params.set("run_id", filters.runId);
  if (filters?.workflowRunId) {
    params.set("workflow_run_id", filters.workflowRunId);
  }
  const query = params.size ? `?${params.toString()}` : "";
  return (await json<{ data: Approval[] }>(await apiFetch(`/v1/workspaces/${workspaceId}/approval-requests${query}`))).data;
}

export async function fetchApprovalRequest(id: string): Promise<Approval> {
  return json<Approval>(await apiFetch(`/v1/approval-requests/${id}`));
}

export async function resolveApproval(id: string, decision: "approve" | "reject"): Promise<Approval> {
  return json<Approval>(await apiFetch(`/v1/approval-requests/${id}:${decision}`, { method: "POST", body: JSON.stringify({}) }));
}
