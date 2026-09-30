import { apiFetch, readApiError } from "./api";

export type EvaluationDataset = {
  id: string; workspace_id: string; name: string; description: string | null;
  case_count: number; created_at: string; updated_at: string;
};
export type EvaluationCase = {
  id: string; evaluation_dataset_id: string; position: number;
  input: { type: "text"; text: string }; expected_output: { text?: string } | null;
  expected_tool: string | null; expected_schema: Record<string, unknown> | null;
  rubric: string | null; metadata: Record<string, unknown>;
};
export type EvaluatorType = "EXACT_MATCH" | "CONTAINS" | "JSON_SCHEMA" | "TOOL_CALL" | "LATENCY" | "LLM_JUDGE" | "GROUNDEDNESS";
export type EvaluationRun = {
  id: string; evaluation_dataset_id: string; agent_id: string; agent_version_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  evaluators: Array<{ type: EvaluatorType; config: Record<string, unknown> }>;
  aggregate_metrics: Record<string, unknown>; error: { code: string; message: string } | null;
  started_at: string | null; completed_at: string | null; created_at: string;
};
export type EvaluationResult = {
  id: string; case_id: string; case: EvaluationCase; run_id: string | null;
  trace_id: string | null;
  evaluator: EvaluatorType; score: number | null; passed: boolean | null;
  details: Record<string, unknown>; created_at: string;
};

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await readApiError(response));
  return response.status === 204 ? undefined as T : await response.json() as T;
}

export async function fetchEvaluationDatasets(workspaceId: string) {
  return (await json<{ data: EvaluationDataset[] }>(await apiFetch(`/v1/workspaces/${workspaceId}/evaluation-datasets`))).data;
}
export async function createEvaluationDataset(workspaceId: string, payload: { name: string; description: string }) {
  return json<EvaluationDataset>(await apiFetch(`/v1/workspaces/${workspaceId}/evaluation-datasets`, { method: "POST", body: JSON.stringify(payload) }));
}
export async function fetchEvaluationDataset(datasetId: string) {
  return json<EvaluationDataset>(await apiFetch(`/v1/evaluation-datasets/${datasetId}`));
}
export async function fetchEvaluationCases(datasetId: string) {
  return (await json<{ data: EvaluationCase[] }>(await apiFetch(`/v1/evaluation-datasets/${datasetId}/cases`))).data;
}
export async function createEvaluationCase(datasetId: string, payload: { input: { type: "text"; text: string }; expected_output: { text: string } | null; expected_tool?: string | null; expected_schema?: Record<string, unknown> | null; rubric?: string | null }) {
  return json<EvaluationCase>(await apiFetch(`/v1/evaluation-datasets/${datasetId}/cases`, { method: "POST", body: JSON.stringify(payload) }));
}
export async function fetchEvaluationRuns(datasetId: string) {
  return (await json<{ data: EvaluationRun[] }>(await apiFetch(`/v1/evaluation-datasets/${datasetId}/runs`))).data;
}
export async function createEvaluationRun(datasetId: string, payload: { agent_version_id: string; evaluators: Array<{ type: EvaluatorType; config?: Record<string, unknown> }> }) {
  return json<EvaluationRun>(await apiFetch(`/v1/evaluation-datasets/${datasetId}/runs`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(payload) }));
}
export async function fetchEvaluationResults(runId: string) {
  return (await json<{ data: EvaluationResult[] }>(await apiFetch(`/v1/evaluation-runs/${runId}/results`))).data;
}
export async function compareEvaluationRuns(baselineRunId: string, candidateRunId: string) {
  return json<{ baseline: { id: string; agent_version_id: string; metrics: Record<string, number | null> }; candidate: { id: string; agent_version_id: string; metrics: Record<string, number | null> }; deltas: Record<string, number | null> }>(await apiFetch("/v1/evaluation-runs:compare", { method: "POST", body: JSON.stringify({ baseline_run_id: baselineRunId, candidate_run_id: candidateRunId }) }));
}
