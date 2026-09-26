import { apiFetch, readApiError } from "./api";

export type MCPAuth = {
  mode: "NONE" | "BEARER" | "HEADER";
  header_name: string;
  prefix: string;
  secret_key: string;
  custom_headers: Array<{
    header_name: string;
    secret_key?: string;
    credential_id?: string;
  }>;
};

export type MCPServer = {
  id: string;
  workspace_id: string;
  name: string;
  transport: "STREAMABLE_HTTP";
  endpoint: string;
  credential_id: string | null;
  status: "ACTIVE" | "DISABLED";
  connection_status: "UNKNOWN" | "CONNECTED" | "FAILED";
  protocol_version: string | null;
  server_info: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  last_error_code: string | null;
  last_tested_at: string | null;
  last_discovered_at: string | null;
  tool_count: number;
  created_at: string;
  updated_at: string;
};

export type MCPTool = {
  id: string;
  mcp_server_id: string;
  remote_name: string;
  title: string | null;
  description: string | null;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown> | null;
  annotations: Record<string, unknown>;
  schema_fingerprint: string;
  available: boolean;
  status: "AVAILABLE" | "IMPORTED" | "CHANGED" | "REMOVED";
  imported_tool_id: string | null;
  latest_imported_tool_version_id: string | null;
  discovered_at: string;
  last_seen_at: string | null;
};

type Collection<T> = {
  data: T[];
  pagination: { next_cursor: string | null; has_more: boolean };
};

export async function fetchMCPServers(workspaceId: string): Promise<MCPServer[]> {
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/mcp-servers`);
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as Collection<MCPServer>).data;
}

export async function createMCPServer(
  workspaceId: string,
  input: { name: string; endpoint: string; credential_id: string | null; auth: MCPAuth },
): Promise<MCPServer> {
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/mcp-servers`, {
    method: "POST",
    body: JSON.stringify({ ...input, transport: "STREAMABLE_HTTP" }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as MCPServer;
}

export async function updateMCPServer(serverId: string, input: Partial<{
  name: string;
  endpoint: string;
  credential_id: string | null;
  auth: MCPAuth;
  status: "ACTIVE" | "DISABLED";
}>) {
  const response = await apiFetch(`/v1/mcp-servers/${serverId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as MCPServer;
}

export async function disableMCPServer(serverId: string) {
  const response = await apiFetch(`/v1/mcp-servers/${serverId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function deleteMCPServer(serverId: string): Promise<void> {
  await disableMCPServer(serverId);
}

export async function testMCPServer(serverId: string) {
  const response = await apiFetch(`/v1/mcp-servers/${serverId}:test`, { method: "POST" });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as { status: "CONNECTED" | "FAILED"; latency_ms: number; error?: { code: string; message: string } };
}

export async function discoverMCPServer(serverId: string) {
  const response = await apiFetch(`/v1/mcp-servers/${serverId}:discover`, { method: "POST" });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as { tools: MCPTool[]; added: number; updated: number; removed: number };
}

export async function fetchMCPTools(serverId: string): Promise<MCPTool[]> {
  const response = await apiFetch(`/v1/mcp-servers/${serverId}/tools`);
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as Collection<MCPTool>).data;
}

export async function importMCPTool(serverId: string, input: {
  remote_name: string;
  tool_name: string;
  slug: string;
  timeout_seconds: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  side_effect: boolean;
  idempotent: boolean;
}) {
  const response = await apiFetch(`/v1/mcp-servers/${serverId}/tools:import`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as { created: boolean; tool_id: string; tool_version_id: string; version_number: number };
}

export async function attachToolToDraft(agentId: string, toolVersionId: string, alias?: string) {
  const response = await apiFetch(`/v1/agents/${agentId}/draft/tools`, {
    method: "POST",
    body: JSON.stringify({ tool_version_id: toolVersionId, alias: alias || null }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
}
