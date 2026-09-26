import { apiFetch, readApiError } from "./api";

export type ModelProviderId = "google" | "openai" | "azure_openai" | "deepseek";

export type ModelConnectionTestPayload = {
  provider: ModelProviderId;
  model_name: string;
  deployment_name?: string;
  base_url?: string;
  api_key: string;
};

export type ModelConnectionTestResult = {
  status: "SUCCESS" | "FAILED";
  provider: ModelProviderId;
  model_name: string;
  latency_ms?: number | null;
  error?: { code: string; message: string } | null;
};

export async function testModelConnection(
  workspaceId: string,
  payload: ModelConnectionTestPayload,
): Promise<ModelConnectionTestResult> {
  const response = await apiFetch(
    `/v1/workspaces/${workspaceId}/model-connections:test`,
    { method: "POST", body: JSON.stringify(payload) },
  );
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as ModelConnectionTestResult;
}
