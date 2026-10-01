import { apiFetch, readApiError } from "./api";

export type Deployment = {
  id: string;
  workspace_id: string;
  agent_id: string;
  agent_name: string;
  agent_version_id: string;
  agent_version_number: number;
  name: string;
  slug: string;
  environment: "DEVELOPMENT" | "STAGING" | "PRODUCTION";
  status: "ACTIVE" | "DISABLED";
  created_at: string;
  updated_at: string;
};

export type DeploymentApiKey = {
  id: string;
  workspace_id: string;
  deployment_id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
};

export type CreatedDeploymentApiKey = DeploymentApiKey & { key: string };
export type AgentVersionSummary = {
  id: string;
  version_number: number;
  change_note: string | null;
  created_at: string;
};

type Collection<T> = {
  data: T[];
  pagination: { next_cursor: string | null; has_more: boolean };
};

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as T;
}

export async function fetchDeployments(workspaceId: string): Promise<Deployment[]> {
  const body = await readJson<Collection<Deployment>>(
    await apiFetch(`/v1/workspaces/${workspaceId}/deployments?limit=100`),
  );
  return body.data;
}

export async function fetchDeployment(deploymentId: string): Promise<Deployment> {
  return readJson<Deployment>(await apiFetch(`/v1/deployments/${deploymentId}`));
}

export async function createDeployment(
  workspaceId: string,
  payload: {
    name: string;
    slug: string;
    agent_id: string;
    agent_version_id: string;
    environment: Deployment["environment"];
  },
): Promise<Deployment> {
  return readJson<Deployment>(await apiFetch(`/v1/workspaces/${workspaceId}/deployments`, {
    method: "POST",
    body: JSON.stringify(payload),
  }));
}

export async function changeDeploymentVersion(
  deploymentId: string,
  agentVersionId: string,
): Promise<Deployment> {
  return readJson<Deployment>(await apiFetch(`/v1/deployments/${deploymentId}`, {
    method: "PATCH",
    body: JSON.stringify({ agent_version_id: agentVersionId }),
  }));
}

export async function setDeploymentStatus(
  deploymentId: string,
  status: Deployment["status"],
): Promise<Deployment> {
  const action = status === "ACTIVE" ? "enable" : "disable";
  return readJson<Deployment>(await apiFetch(`/v1/deployments/${deploymentId}:${action}`, {
    method: "POST",
  }));
}

export async function fetchDeploymentApiKeys(deploymentId: string): Promise<DeploymentApiKey[]> {
  const body = await readJson<Collection<DeploymentApiKey>>(
    await apiFetch(`/v1/deployments/${deploymentId}/api-keys?limit=100`),
  );
  return body.data;
}

export async function createDeploymentApiKey(
  deploymentId: string,
  name: string,
): Promise<CreatedDeploymentApiKey> {
  return readJson<CreatedDeploymentApiKey>(
    await apiFetch(`/v1/deployments/${deploymentId}/api-keys`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  );
}

export async function revokeDeploymentApiKey(apiKeyId: string): Promise<void> {
  const response = await apiFetch(`/v1/api-keys/${apiKeyId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}
