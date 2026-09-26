import { apiFetch, readApiError } from "./api";

export type KnowledgeBase = {
    id: string; workspace_id: string; name: string; description: string | null;
    status: "ACTIVE" | "ARCHIVED"; embedding_model: string; embedding_revision: string;
    embedding_dimensions: number; document_count: number; ready_document_count: number;
    metadata: Record<string, unknown>; created_at: string; updated_at: string;
};
export type Document = { id: string; knowledge_base_id: string; filename: string; mime_type: string; size_bytes: number; status: string; ingestion_generation: number; active_generation: number | null; is_queryable: boolean; page_count: number | null; chunk_count: number; token_count: number; error_code: string | null; error_message: string | null; created_at: string; updated_at: string; };
export type Page<T> = { data: T[]; pagination: { next_cursor: string | null; has_more: boolean } };
export type KnowledgeBinding = { knowledge_base_id: string; name: string; status: string; retrieval_config: { mode?: "auto" | "always"; top_k?: number; score_threshold?: number | null } };

async function json<T>(path: string, init?: RequestInit): Promise<T> { const response = await apiFetch(path, init); if (!response.ok) throw new Error(await readApiError(response)); return response.json() as Promise<T>; }
export function listKnowledgeBases(workspaceId: string, cursor?: string, status?: KnowledgeBase["status"], limit = 12) { const params = new URLSearchParams({ limit: String(limit) }); if (cursor) params.set("cursor", cursor); if (status) params.set("status", status); return json<Page<KnowledgeBase>>(`/v1/workspaces/${workspaceId}/knowledge-bases?${params.toString()}`); }
export function createKnowledgeBase(workspaceId: string, payload: { name: string; description?: string }) { return json<KnowledgeBase>(`/v1/workspaces/${workspaceId}/knowledge-bases`, { method: "POST", body: JSON.stringify(payload) }); }
export function archiveKnowledgeBase(id: string) { return apiFetch(`/v1/knowledge-bases/${id}`, { method: "DELETE" }).then(async (response) => { if (!response.ok) throw new Error(await readApiError(response)); }); }
export function getKnowledgeBase(id: string) { return json<KnowledgeBase>(`/v1/knowledge-bases/${id}`); }
export function listDocuments(id: string) { return json<Page<Document>>(`/v1/knowledge-bases/${id}/documents`); }
export function uploadDocument(id: string, file: File) { const body = new FormData(); body.append("file", file); return json<Document>(`/v1/knowledge-bases/${id}/documents`, { method: "POST", body, headers: { "Idempotency-Key": crypto.randomUUID() } }); }
export function reprocessDocument(id: string) { return json<Document>(`/v1/documents/${id}:reprocess`, { method: "POST" }); }
export function deleteDocument(id: string) { return apiFetch(`/v1/documents/${id}`, { method: "DELETE" }).then(async (response) => { if (!response.ok) throw new Error(await readApiError(response)); }); }
export function listDraftKnowledge(agentId: string) { return json<{ data: KnowledgeBinding[] }>(`/v1/agents/${agentId}/draft/knowledge-bases`); }
export function attachDraftKnowledge(agentId: string, knowledgeBaseId: string, topK = 5) { return json<KnowledgeBinding>(`/v1/agents/${agentId}/draft/knowledge-bases`, { method: "POST", body: JSON.stringify({ knowledge_base_id: knowledgeBaseId, top_k: topK }) }); }
export function detachDraftKnowledge(agentId: string, knowledgeBaseId: string) { return apiFetch(`/v1/agents/${agentId}/draft/knowledge-bases/${knowledgeBaseId}`, { method: "DELETE" }).then(async (response) => { if (!response.ok) throw new Error(await readApiError(response)); }); }
