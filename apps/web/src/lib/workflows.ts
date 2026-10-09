import { apiFetch, readApiErrorDetails } from "./api";

export type Workflow = {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  status: "ACTIVE" | "ARCHIVED";
  latest_version_number: number;
  created_at: string;
  updated_at: string;
};

export type WorkflowNode = {
  key: string;
  type: "START" | "END" | "AGENT" | "TOOL" | "CONDITION" | "TRANSFORM" | "APPROVAL";
  name: string;
  config: Record<string, unknown>;
  position?: { x: number; y: number } | null;
};

export type WorkflowEdge = {
  source: string;
  target: string;
  source_handle?: string | null;
  priority?: number;
};

export type WorkflowExecutionBudget = {
  max_node_executions: number;
  max_agent_runs: number;
  max_model_calls: number;
  max_tool_calls: number;
  max_child_runs: number;
  max_agent_depth: number;
  max_total_steps: number;
  max_total_tokens: number;
  timeout_seconds: number;
};

export type WorkflowDefinition = {
  schema_version: 1;
  configuration: Record<string, unknown>;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport?: { x: number; y: number; zoom: number } | null;
};

export type WorkflowInputSchema = {
  type: "object";
  properties: Record<string, { type: "string" | "integer" | "number" | "boolean" | "object" | "array"; title?: string; description?: string; default?: unknown; enum?: unknown[] }>;
  required: string[];
  additionalProperties: false;
};

export type WorkflowChatConfig = { enabled: boolean; description?: string; connection_id?: string | null; model?: string | null };

export type WorkflowVersion = { id: string; workflow_id: string; version_number: number; configuration: Record<string, unknown>; definition: WorkflowDefinition };

export type WorkflowChatSession = { id: string; workflow_id: string; workflow_version_id: string; title: string | null; collected_input: Record<string, unknown>; active_run_id: string | null; created_at: string; updated_at: string };
export type WorkflowChatMessage = { id: string; sequence_no: number; role: "USER" | "ASSISTANT"; kind: "TEXT" | "WORKFLOW_RUN"; content: Record<string, unknown>; workflow_run_id: string | null; created_at: string };
export type WorkflowChatTurn = { id: string; chat_session_id: string; status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED"; decision: { action: string; reply: string; input: Record<string, unknown> } | null; error: { code: string; message: string } | null; model_usage: Record<string, unknown>; workflow_run_id: string | null; trace_id: string | null; created_at: string; completed_at: string | null };

export type WorkflowDraft = {
  workflow_id: string;
  revision: number;
  definition: WorkflowDefinition;
  updated_at: string;
};

export type WorkflowRun = {
  id: string;
  workflow_id: string;
  workflow_version_id: string;
  trace_id: string;
  status: "QUEUED" | "RUNNING" | "WAITING_APPROVAL" | "COMPLETED" | "FAILED" | "CANCELLED";
  current_node_key: string | null;
  current_node_name: string | null;
  input: Record<string, unknown>;
  variables: Record<string, unknown>;
  node_outputs: Record<string, unknown>;
  output: Record<string, unknown> | null;
  usage: Record<string, unknown>;
  execution_budget: Record<string, unknown>;
  error: { code: string; message: string } | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type WorkflowRunSummary = Pick<WorkflowRun, "id" | "workflow_id" | "workflow_version_id" | "trace_id" | "status" | "current_node_key" | "current_node_name" | "output" | "usage" | "started_at" | "completed_at" | "created_at">;

export type WorkflowNodeRun = {
  id: string;
  node_key: string;
  node_name: string;
  node_type: "START" | "END" | "AGENT" | "TOOL" | "CONDITION" | "TRANSFORM" | "APPROVAL";
  status: "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  attempt: number;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  agent_run_id: string | null;
  span_id: string | null;
  usage: Record<string, unknown>;
  duration_ms: number | null;
  started_at: string;
  completed_at: string | null;
};

export type WorkflowEvent = {
  sequence: number;
  event: string;
  workflow_run_id: string;
  node_run_id: string | null;
  occurred_at: string;
  data: Record<string, unknown>;
};

export type ChildRun = {
  id: string;
  agent_id: string;
  agent_version_id: string;
  session_id: string | null;
  parent_run_id: string | null;
  root_run_id: string;
  agent_depth: number;
  trace_id: string;
  status: string;
  usage: Record<string, unknown>;
  error: { code: string; message: string } | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw await readApiErrorDetails(response);
  return response.json() as Promise<T>;
}

export async function fetchWorkflows(workspaceId: string): Promise<Workflow[]> {
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/workflows`);
  return (await json<{ data: Workflow[] }>(response)).data;
}

export async function createWorkflow(workspaceId: string, payload: { name: string; slug: string; description?: string }) {
  return json<Workflow>(await apiFetch(`/v1/workspaces/${workspaceId}/workflows`, { method: "POST", body: JSON.stringify(payload) }));
}

export async function fetchWorkflow(workflowId: string) {
  return json<Workflow>(await apiFetch(`/v1/workflows/${workflowId}`));
}

export async function updateWorkflow(workflowId: string, payload: { name?: string; description?: string | null }) {
  return json<Workflow>(await apiFetch(`/v1/workflows/${workflowId}`, { method: "PATCH", body: JSON.stringify(payload) }));
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  const response = await apiFetch(`/v1/workflows/${workflowId}`, { method: "DELETE" });
  if (!response.ok) throw await readApiErrorDetails(response);
}

export async function fetchWorkflowDraft(workflowId: string) {
  return json<WorkflowDraft>(await apiFetch(`/v1/workflows/${workflowId}/draft`));
}

export async function saveWorkflowDraft(workflowId: string, revision: number, definition: WorkflowDefinition) {
  return json<WorkflowDraft>(await apiFetch(`/v1/workflows/${workflowId}/draft`, { method: "PUT", body: JSON.stringify({ expected_revision: revision, definition }) }));
}

export async function validateWorkflowDraft(workflowId: string) {
  return json<{ valid: boolean; errors: Array<{ code: string; message: string; node_key?: string; field?: string }> }>(await apiFetch(`/v1/workflows/${workflowId}/draft:validate`, { method: "POST" }));
}

export async function publishWorkflow(workflowId: string) {
  return json<{ id: string; version_number: number }>(await apiFetch(`/v1/workflows/${workflowId}/versions`, { method: "POST" }));
}

export async function fetchWorkflowVersions(workflowId: string) {
  const body = await json<{ data: Array<{ id: string; version_number: number; configuration?: Record<string, unknown> }> }>(await apiFetch(`/v1/workflows/${workflowId}/versions`));
  return body.data;
}

export async function fetchWorkflowVersion(versionId: string) { return json<WorkflowVersion>(await apiFetch(`/v1/workflow-versions/${versionId}`)); }

export async function createWorkflowChat(workflowId: string, workflowVersionId: string) { return json<WorkflowChatSession>(await apiFetch(`/v1/workflows/${workflowId}/chats`, { method: "POST", body: JSON.stringify({ workflow_version_id: workflowVersionId }) })); }
export async function fetchWorkflowChats(workflowId: string) { return (await json<{ data: WorkflowChatSession[] }>(await apiFetch(`/v1/workflows/${workflowId}/chats`))).data; }
export async function fetchWorkflowChat(chatId: string) { return json<WorkflowChatSession>(await apiFetch(`/v1/workflow-chats/${chatId}`)); }
export async function fetchWorkflowChatMessages(chatId: string, after = 0) { return (await json<{ data: WorkflowChatMessage[]; pagination: { next_cursor: number | null; has_more: boolean } }>(await apiFetch(`/v1/workflow-chats/${chatId}/messages?after=${after}&limit=100`))); }
export async function createWorkflowChatTurn(chatId: string, message: string, idempotencyKey: string) { return json<WorkflowChatTurn>(await apiFetch(`/v1/workflow-chats/${chatId}/turns`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify({ message }) })); }
export async function fetchWorkflowChatTurn(turnId: string) { return json<WorkflowChatTurn>(await apiFetch(`/v1/workflow-chat-turns/${turnId}`)); }

export async function runWorkflow(workflowId: string, workflowVersionId: string, input: Record<string, unknown>) {
  return json<WorkflowRun>(await apiFetch(`/v1/workflows/${workflowId}/runs`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ workflow_version_id: workflowVersionId, input, execution_mode: "async" }) }));
}

export async function fetchWorkflowRun(runId: string) {
  return json<WorkflowRun>(await apiFetch(`/v1/workflow-runs/${runId}`));
}

export async function cancelWorkflowRun(runId: string) { return json<WorkflowRun>(await apiFetch(`/v1/workflow-runs/${runId}:cancel`, { method: "POST" })); }

export async function fetchWorkflowRuns(workflowId: string, limit = 50) {
  const body = await json<{ data: WorkflowRunSummary[]; pagination: { next_cursor: string | null; has_more: boolean } }>(await apiFetch(`/v1/workflows/${workflowId}/runs?limit=${limit}`));
  return body;
}

export async function fetchWorkflowNodeRuns(runId: string) {
  const body = await json<{ data: WorkflowNodeRun[] }>(await apiFetch(`/v1/workflow-runs/${runId}/nodes`));
  return body.data;
}

export async function fetchWorkflowEvents(runId: string, after = 0) {
  const response = await apiFetch(`/v1/workflow-runs/${runId}/events`, { headers: { "Last-Event-ID": String(after) } });
  if (!response.ok) throw await readApiErrorDetails(response);
  const body = await response.text();
  return body.split("\n\n").flatMap((block) => {
    const line = block.split("\n").find((item) => item.startsWith("data:"));
    if (!line) return [];
    try { return [JSON.parse(line.slice(5)) as WorkflowEvent]; } catch { return []; }
  });
}

export async function fetchRunChildren(runId: string): Promise<ChildRun[]> {
  const body = await json<{ data: ChildRun[] }>(await apiFetch(`/v1/runs/${runId}/children?limit=100`));
  return body.data;
}
