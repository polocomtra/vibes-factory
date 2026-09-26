import { apiFetch, readApiError } from "./api";

export type AgentStatus = "ACTIVE" | "ARCHIVED";

export type ModelDefinition = {
  provider: string;
  name: string;
  display_name: string;
  capabilities: Record<string, boolean>;
  context_window?: number | null;
  max_output_tokens?: number | null;
  is_default?: boolean;
};

export type ModelConfiguration = {
  provider: string;
  name: string;
  config: Record<string, unknown>;
  reasoning_options: Record<string, unknown>;
  provider_options: Record<string, unknown>;
};

export type RuntimeConfiguration = {
  max_steps: number;
  max_model_calls: number;
  max_tool_calls: number;
  max_child_runs: number;
  max_agent_depth: number;
  max_total_tokens: number;
  timeout_seconds: number;
};

export type MemoryConfiguration = {
  enabled: boolean;
  memory_store_id: string | null;
  retrieve: { top_k: number };
  write: { enabled: boolean; types: Array<"PROFILE" | "SEMANTIC" | "SUMMARY" | "PROCEDURAL"> };
};

export type Agent = {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  status: AgentStatus;
  latest_version_number: number;
  is_supervisor?: boolean;
  created_at: string;
  updated_at: string;
};

export type AgentDraft = {
  agent_id: string;
  instructions: string;
  model: ModelConfiguration;
  runtime_config: RuntimeConfiguration;
  memory_config: MemoryConfiguration;
  guardrails_enabled: boolean;
  updated_at: string;
};

export type AgentVersionSummary = {
  id: string;
  agent_id: string;
  version_number: number;
  change_note: string | null;
  created_at: string;
};

export type AgentVersion = AgentVersionSummary & {
  instructions: string;
  model: ModelConfiguration;
  runtime_config: RuntimeConfiguration;
  memory_config: MemoryConfiguration;
  guardrails_enabled: boolean;
  snapshot: Record<string, unknown>;
  child_agent_bindings?: ChildAgentBinding[];
};

export type ChildAgentBinding = {
  child_agent_id: string;
  child_agent_version_id: string;
  alias: string;
  description: string | null;
};

type Collection<T> = { data: T[]; pagination: { next_cursor: string | null; has_more: boolean } };

export async function fetchModels(): Promise<ModelDefinition[]> {
  const response = await apiFetch("/v1/models");
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as { data: ModelDefinition[] }).data;
}

export async function fetchAgents(workspaceId: string, search = "", status = ""): Promise<Agent[]> {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/agents${suffix}`);
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as Collection<Agent>).data;
}

export async function fetchAgent(agentId: string): Promise<Agent> {
  const response = await apiFetch(`/v1/agents/${agentId}`);
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as Agent;
}

export async function deleteAgent(agentId: string): Promise<void> {
  const response = await apiFetch(`/v1/agents/${agentId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function fetchDraft(agentId: string): Promise<AgentDraft> {
  const response = await apiFetch(`/v1/agents/${agentId}/draft`);
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as AgentDraft;
}

export async function fetchVersions(agentId: string): Promise<AgentVersionSummary[]> {
  const response = await apiFetch(`/v1/agents/${agentId}/versions`);
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as Collection<AgentVersionSummary>).data;
}

export async function fetchVersion(agentId: string, versionId: string): Promise<AgentVersion> {
  const response = await apiFetch(`/v1/agents/${agentId}/versions/${versionId}`);
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as AgentVersion;
}

export async function fetchChildAgentBindings(agentId: string): Promise<ChildAgentBinding[]> {
  const response = await apiFetch(`/v1/agents/${agentId}/draft/child-agents`);
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as ChildAgentBinding[];
}

export async function addChildAgentBinding(
  agentId: string,
  payload: Omit<ChildAgentBinding, "description"> & { description?: string | null },
): Promise<ChildAgentBinding> {
  const response = await apiFetch(`/v1/agents/${agentId}/draft/child-agents`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as ChildAgentBinding;
}

export async function deleteChildAgentBinding(agentId: string, childAgentId: string): Promise<void> {
  const response = await apiFetch(`/v1/agents/${agentId}/draft/child-agents/${childAgentId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}
