import { apiFetch, readApiError } from "./api";

export type MemoryType = "PROFILE" | "SEMANTIC" | "SUMMARY" | "PROCEDURAL";

export type MemoryStore = {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  embedding_provider: string;
  embedding_model: string;
  embedding_revision: string;
  embedding_dimensions: number;
  configuration: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type MemoryItem = {
  id: string;
  workspace_id: string;
  memory_store_id: string;
  user_id: string | null;
  agent_id: string | null;
  type: MemoryType;
  content: string;
  importance: number | null;
  confidence: number | null;
  source_session_id: string | null;
  source_run_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
};

export type MemoryPage = {
  data: MemoryItem[];
  pagination: { next_cursor: string | null; has_more: boolean };
};

export type MemoryStorePage = {
  data: MemoryStore[];
  pagination: { next_cursor: string | null; has_more: boolean };
};

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as T;
}

export async function listMemoryStores(
  workspaceId: string,
  cursor?: string,
  limit = 12,
): Promise<MemoryStorePage> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return json<MemoryStorePage>(
    `/v1/workspaces/${workspaceId}/memory-stores?${params.toString()}`,
  );
}

export async function createMemoryStore(
  workspaceId: string,
  input: { name: string; description?: string },
): Promise<MemoryStore> {
  return json<MemoryStore>(`/v1/workspaces/${workspaceId}/memory-stores`, {
    method: "POST",
    body: JSON.stringify({ name: input.name, description: input.description || null }),
  });
}

export async function listMemoryItems(
  storeId: string,
  filters: { agentId?: string; type?: MemoryType; cursor?: string; limit?: number } = {},
): Promise<MemoryPage> {
  const params = new URLSearchParams();
  params.set("limit", String(filters.limit ?? 12));
  if (filters.agentId) params.set("agent_id", filters.agentId);
  if (filters.type) params.set("type", filters.type);
  if (filters.cursor) params.set("cursor", filters.cursor);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return json<MemoryPage>(`/v1/memory-stores/${storeId}/items${suffix}`);
}

export async function searchMemory(
  storeId: string,
  input: { query: string; agent_id?: string; top_k?: number },
): Promise<{ data: MemoryItem[]; query: string; model: string; latency_ms: number }> {
  return json(`/v1/memory-stores/${storeId}:search`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function createMemoryItem(
  storeId: string,
  input: {
    agent_id?: string | null;
    type: MemoryType;
    content: string;
    importance?: number | null;
    confidence?: number | null;
    expires_at?: string | null;
  },
): Promise<MemoryItem> {
  return json<MemoryItem>(`/v1/memory-stores/${storeId}/items`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateMemoryItem(
  itemId: string,
  input: Partial<Pick<MemoryItem, "content" | "type" | "importance" | "confidence" | "expires_at">>,
): Promise<MemoryItem> {
  return json<MemoryItem>(`/v1/memory-items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function deleteMemoryItem(itemId: string): Promise<void> {
  const response = await apiFetch(`/v1/memory-items/${itemId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}
