import { apiFetch, readApiError } from "./api";

export type MonitoringFilters = {
  from: string;
  to: string;
  agent_id: string;
  agent_version_id: string;
  provider: string;
  model: string;
  status: string;
};

export type MonitoringSummary = {
  period: { from: string; to: string };
  filters: Record<string, string | null>;
  runs: { total: number; completed: number; failed: number; cancelled: number; in_progress: number; success_rate: number | null; failure_rate: number | null };
  latency: { average_ms: number | null; p95_ms: number | null };
  model_latency: { average_ms: number | null };
  usage: { input_tokens: number; output_tokens: number };
  estimated_cost: string | null;
  currency: "USD";
  tool_failures: { count: number; rate: number | null };
  data_quality: { accounted_runs: number; legacy_runs: number; usage_complete_runs: number; cost_complete_runs: number; missing_pricing_or_usage_calls: number; estimated_input_calls: number; estimated_output_calls: number; cost_complete: boolean };
};

export type MonitoringPoint = { timestamp: string; value: number | null; complete: boolean };
export type MonitoringSeries = { metric: string; interval: "1h" | "1d"; points: MonitoringPoint[] };
export type MonitoringOptions = { agents: Array<{ id: string; name: string }>; models: Array<{ provider: string; model: string }> };

function query(filters: MonitoringFilters) {
  const params = new URLSearchParams();
  for (const key of Object.keys(filters) as (keyof MonitoringFilters)[]) {
    if (filters[key]) params.set(key, filters[key]);
  }
  return params;
}

async function read<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as T;
}

export async function fetchMonitoringOptions(workspaceId: string, signal?: AbortSignal) {
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/monitoring/options`, { signal });
  return read<MonitoringOptions>(response);
}

export async function fetchMonitoringSummary(workspaceId: string, filters: MonitoringFilters, signal?: AbortSignal) {
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/monitoring/summary?${query(filters)}`, { signal });
  return read<MonitoringSummary>(response);
}

export async function fetchMonitoringSeries(workspaceId: string, metric: string, filters: MonitoringFilters, signal?: AbortSignal) {
  const params = query(filters);
  params.set("metric", metric);
  params.set("interval", "auto");
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/monitoring/timeseries?${params}`, { signal });
  return read<MonitoringSeries>(response);
}
