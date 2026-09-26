import { apiFetch, readApiError } from "./api";

export type Credential = {
  id: string;
  workspace_id: string;
  name: string;
  provider: string;
  type: string;
  metadata: Record<string, unknown>;
  status: "ACTIVE" | "REVOKED";
  created_at: string;
  updated_at: string;
  revoked_at: string | null;
};

type CredentialCollection = {
  data: Credential[];
  pagination: { next_cursor: string | null; has_more: boolean };
};

export type CreateCredentialInput = {
  name: string;
  provider: string;
  type: "API_KEY";
  secret: { token: string };
  metadata?: Record<string, unknown>;
};

export async function fetchCredentials(workspaceId: string): Promise<Credential[]> {
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/credentials`);
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as CredentialCollection).data;
}

export async function fetchCredentialKeys(credentialId: string): Promise<string[]> {
  const response = await apiFetch(`/v1/credentials/${credentialId}/keys`);
  if (!response.ok) throw new Error(await readApiError(response));
  return (await response.json() as { credential_id: string; keys: string[] }).keys;
}

export async function createCredential(
  workspaceId: string,
  input: CreateCredentialInput,
): Promise<Credential> {
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/credentials`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as Credential;
}

export async function rotateCredential(
  credentialId: string,
  token: string,
): Promise<Credential> {
  const response = await apiFetch(`/v1/credentials/${credentialId}:rotate`, {
    method: "POST",
    body: JSON.stringify({ secret: { token } }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as Credential;
}

export async function revokeCredential(credentialId: string): Promise<void> {
  const response = await apiFetch(`/v1/credentials/${credentialId}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await readApiError(response));
}
