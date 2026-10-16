import { apiFetch, readApiError } from "./api";

export type ModelProviderId = "azure_openai" | "google" | "deepseek" | "openrouter";
export type ModelConnection = {
  id: string;
  workspace_id: string;
  name: string;
  provider: ModelProviderId;
  credential_id: string;
  base_url: string | null;
  status: "ACTIVE" | "REVOKED";
  created_at: string;
  updated_at: string;
};
export type DiscoveredModel = {
  name: string;
  display_name: string;
  capabilities: Record<string, boolean>;
  context_window: number | null;
  max_output_tokens: number | null;
};

export async function fetchModelConnections(workspaceId: string): Promise<ModelConnection[]> {
  const connections: ModelConnection[] = [];
  let cursor: string | null = null;
  do {
    const params = new URLSearchParams({ limit: "100" });
    if (cursor) params.set("cursor", cursor);
    const response = await apiFetch(`/v1/workspaces/${workspaceId}/model-connections?${params}`);
    if (!response.ok) throw new Error(await readApiError(response));
    const page = await response.json() as {
      data: ModelConnection[];
      pagination: { next_cursor: string | null; has_more: boolean };
    };
    connections.push(...page.data);
    cursor = page.pagination.has_more ? page.pagination.next_cursor : null;
  } while (cursor);
  return connections;
}

export async function fetchModelConnection(id: string): Promise<ModelConnection> {
  const response = await apiFetch(`/v1/model-connections/${id}`);
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as ModelConnection;
}

export async function createModelConnection(
  workspaceId: string,
  payload: { name: string; provider: ModelProviderId; api_key: string; base_url?: string },
): Promise<ModelConnection> {
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/model-connections`, {
    method: "POST", body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as ModelConnection;
}

export async function renameModelConnection(id: string, name: string): Promise<ModelConnection> {
  const response = await apiFetch(`/v1/model-connections/${id}`, {
    method: "PATCH", body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as ModelConnection;
}

export async function revokeModelConnection(id: string): Promise<void> {
  const response = await apiFetch(`/v1/model-connections/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function rotateModelConnectionKey(id: string, apiKey: string): Promise<void> {
  const connection = await fetchModelConnection(id);
  const response = await apiFetch(`/v1/credentials/${connection.credential_id}:rotate`, {
    method: "POST", body: JSON.stringify({ secret: { api_key: apiKey } }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function discoverModels(id: string): Promise<DiscoveredModel[]> {
  const response = await apiFetch(`/v1/model-connections/${id}/models`);
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as { data: DiscoveredModel[] }).data;
}

export async function testSavedModelConnection(
  id: string,
  payload: { model_name: string; deployment_name?: string; probe_planning?: boolean },
): Promise<{ status: "SUCCESS" | "FAILED"; provider: string; model_name: string; latency_ms?: number; capabilities?: Record<string, boolean> | null; error?: { code: string; message: string } | null }> {
  const response = await apiFetch(`/v1/model-connections/${id}:test`, {
    method: "POST", body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json();
}
