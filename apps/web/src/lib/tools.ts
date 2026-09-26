import { apiFetch, readApiError } from "./api";

export type ToolVersion = {
  id: string;
  version_number: number;
  name: string;
  executor_type: "FUNCTION" | "HTTP" | "MCP";
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  created_at: string;
};

export type ToolVersionDetail = ToolVersion & {
  tool_id: string;
  workspace_id: string;
  description: string | null;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown> | null;
  executor: { type: string; config: Record<string, unknown> };
};

export type Tool = {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  type: "FUNCTION" | "HTTP" | "MCP";
  status: "ACTIVE" | "ARCHIVED";
  latest_version_number: number;
  built_in: boolean;
  mcp_server_id: string | null;
  mcp_server_name: string | null;
  versions: ToolVersion[];
  created_at: string;
  updated_at: string;
};

export type ToolCollection = {
  data: Tool[];
  pagination: { next_cursor: string | null; has_more: boolean };
};

export type ToolTestResult = {
  status: "completed" | "failed";
  output?: { query?: string; results?: Array<{ title: string; url: string; published_date?: string | null; highlights: string[] }> };
  error?: { code: string; message: string };
  duration_ms: number;
};

export type DraftTool = {
  tool_version_id: string;
  tool_id: string;
  name: string;
  description: string | null;
  alias: string | null;
  enabled: boolean;
  version_number: number;
};

export type CreateToolInput = {
  name: string;
  slug: string;
  description: string | null;
  type: "HTTP";
};

export type CreateToolVersionInput = {
  name: string;
  description: string | null;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown> | null;
  executor: { type: "HTTP"; config: Record<string, unknown> };
  timeout_seconds: number;
  retry_policy: Record<string, unknown>;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  side_effect: boolean;
  idempotent: boolean;
};

export async function fetchTools(workspaceId: string): Promise<Tool[]> {
  const response = await apiFetch("/v1/workspaces/" + workspaceId + "/tools");
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as ToolCollection).data;
}

export async function deleteTool(toolId: string): Promise<void> {
  const response = await apiFetch(`/v1/tools/${toolId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function testTool(versionId: string, arguments_: Record<string, unknown>): Promise<ToolTestResult> {
  const response = await apiFetch("/v1/tool-versions/" + versionId + ":test", {
    method: "POST",
    body: JSON.stringify({ arguments: arguments_ }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as ToolTestResult;
}

export async function fetchDraftTools(agentId: string): Promise<DraftTool[]> {
  const response = await apiFetch("/v1/agents/" + agentId + "/draft/tools");
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as { data: DraftTool[] }).data;
}

export async function fetchToolVersion(toolId: string, versionId: string): Promise<ToolVersionDetail> {
  const response = await apiFetch("/v1/tools/" + toolId + "/versions/" + versionId);
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as ToolVersionDetail;
}

export async function createTool(workspaceId: string, input: CreateToolInput): Promise<Tool> {
  const response = await apiFetch("/v1/workspaces/" + workspaceId + "/tools", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as Tool;
}

export async function createToolVersion(toolId: string, input: CreateToolVersionInput): Promise<ToolVersionDetail> {
  const response = await apiFetch("/v1/tools/" + toolId + "/versions", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as ToolVersionDetail;
}
