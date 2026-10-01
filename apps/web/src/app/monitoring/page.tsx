"use client";

import { Activity, AlertTriangle, CircleDollarSign, Clock3, RefreshCw, Timer, Workflow } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell, useSelectedWorkspaceId } from "../../components/app-shell";
import { PrimarySelect, type PrimarySelectOption } from "../../components/primary-select";
import { PrimaryTextInput } from "../../components/primary-text-field";
import { fetchVersions, type AgentVersionSummary } from "../../lib/agents";
import { fetchMonitoringOptions, fetchMonitoringSeries, fetchMonitoringSummary, type MonitoringFilters, type MonitoringPoint, type MonitoringSeries, type MonitoringSummary } from "../../lib/monitoring";

const metricDefinitions = [
  { key: "runs", title: "Runs", color: "var(--brand-primary)", format: (value: number | null) => integer(value) },
  { key: "success_rate", title: "Success rate", color: "var(--brand-secondary)", format: (value: number | null) => percent(value) },
  { key: "p95_latency", title: "P95 latency", color: "var(--info)", format: (value: number | null) => duration(value) },
  { key: "estimated_cost", title: "Estimated cost · USD", color: "var(--success)", format: (value: number | null) => money(value) },
];

function integer(value: number | null | undefined) { return value == null ? "—" : new Intl.NumberFormat().format(value); }
function percent(value: number | null | undefined) { return value == null ? "—" : `${(value * 100).toFixed(1)}%`; }
function duration(value: number | null | undefined) { return value == null ? "—" : value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`; }
function money(value: number | string | null | undefined) { return value == null ? "—" : new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 4 }).format(Number(value)); }
function toLocalInput(value: Date) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}
function defaultFilters(): MonitoringFilters {
  const to = new Date();
  const from = new Date(to.getTime() - 7 * 86_400_000);
  return { from: from.toISOString(), to: to.toISOString(), agent_id: "", agent_version_id: "", provider: "", model: "", status: "" };
}
function fromUrl(): MonitoringFilters {
  const defaults = defaultFilters();
  const params = new URLSearchParams(window.location.search);
  for (const key of Object.keys(defaults) as (keyof MonitoringFilters)[]) {
    const value = params.get(key);
    if (value) defaults[key] = value;
  }
  return defaults;
}

function MetricCard({ label, value, detail, icon: Icon, tone }: { label: string; value: string; detail: string; icon: typeof Activity; tone: string }) {
  return <article className={`monitoring-metric metric-${tone}`}><div className="monitoring-metric-heading"><span>{label}</span><Icon size={16} aria-hidden="true" /></div><strong>{value}</strong><small>{detail}</small></article>;
}

function TimeSeriesChart({ title, color, series, format }: { title: string; color: string; series: MonitoringSeries | undefined; format: (value: number | null) => string }) {
  const points = series?.points ?? [];
  const known = points.filter((point) => point.value != null);
  const min = Math.min(...known.map((point) => point.value ?? 0), 0);
  const max = Math.max(...known.map((point) => point.value ?? 0), 1);
  const coordinates = known.map((point) => ({ point, x: points.length < 2 ? 0 : (points.indexOf(point) / (points.length - 1)) * 1000, y: 170 - (((point.value ?? 0) - min) / (max - min || 1)) * 150 }));
  const path = coordinates.map(({ x, y }, index) => `${index ? "L" : "M"}${x},${y}`).join(" ");
  const values = known.map((point) => point.value ?? 0);
  const first = points[0]?.timestamp;
  const last = points[points.length - 1]?.timestamp;
  const label = `${title}: ${known.length} data points${known.length ? `, values from ${format(Math.min(...values))} to ${format(Math.max(...values))}` : ""}.`;
  return <article className="panel monitoring-chart-card"><div className="monitoring-chart-heading"><div><span className="panel-kicker">Operational trend</span><h2>{title}</h2></div><span className="monitoring-chart-unit">{series?.interval ?? "—"}</span></div>
    {known.length ? <svg className="monitoring-chart" viewBox="0 0 1000 200" preserveAspectRatio="none" role="img" aria-label={label}>
      {[20, 60, 100, 140, 180].map((y) => <line key={y} x1="0" x2="1000" y1={y} y2={y} className="monitoring-chart-gridline" />)}
      {coordinates.length > 1 ? <path d={path} fill="none" stroke={color} strokeWidth="3" vectorEffect="non-scaling-stroke" /> : null}
      {coordinates.map(({ point, x, y }) => <circle key={point.timestamp} cx={x} cy={y} r="5" fill={color} tabIndex={0} aria-label={`${new Date(point.timestamp).toLocaleString()}: ${format(point.value)}`}><title>{new Date(point.timestamp).toLocaleString()} · {format(point.value)}</title></circle>)}
    </svg> : <div className="monitoring-chart-empty">No data in this interval.</div>}
    <div className="monitoring-chart-axis"><span>{first ? new Date(first).toLocaleString() : "—"}</span><span>{last ? new Date(last).toLocaleString() : "—"}</span></div>
    <details className="monitoring-data-table"><summary>View chart data table</summary><div className="table-scroll"><table><thead><tr><th scope="col">Time</th><th scope="col">Value</th><th scope="col">Coverage</th></tr></thead><tbody>{points.map((point) => <tr key={point.timestamp}><td>{new Date(point.timestamp).toLocaleString()}</td><td>{format(point.value)}</td><td>{point.complete ? "Complete" : "Partial"}</td></tr>)}</tbody></table></div></details>
  </article>;
}

function MonitoringContent() {
  const workspaceId = useSelectedWorkspaceId();
  const [filters, setFilters] = useState<MonitoringFilters>(defaultFilters);
  const [applied, setApplied] = useState<MonitoringFilters>(defaultFilters);
  const [preset, setPreset] = useState("7d");
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [series, setSeries] = useState<Record<string, MonitoringSeries>>({});
  const [agents, setAgents] = useState<PrimarySelectOption[]>([]);
  const [versions, setVersions] = useState<PrimarySelectOption[]>([]);
  const [models, setModels] = useState<PrimarySelectOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState("");
  const [updatedAt, setUpdatedAt] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [readyFromUrl, setReadyFromUrl] = useState(false);
  const [validationError, setValidationError] = useState("");

  useEffect(() => {
    const initial = fromUrl();
    setFilters(initial);
    setApplied(initial);
    if (window.location.search) setPreset("custom");
    setReadyFromUrl(true);
    const onPopState = () => { const next = fromUrl(); setFilters(next); setApplied(next); setPreset("custom"); };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (!readyFromUrl || !workspaceId) return;
    const controller = new AbortController();
    setSummary(null); setSeries({}); setFailed("");
    setFilters((current) => current.agent_id || current.agent_version_id || current.provider || current.model
      ? { ...current, agent_id: "", agent_version_id: "", provider: "", model: "" }
      : current);
    setApplied((current) => current.agent_id || current.agent_version_id || current.provider || current.model
      ? { ...current, agent_id: "", agent_version_id: "", provider: "", model: "" }
      : current);
    const workspaceParams = new URLSearchParams(window.location.search);
    for (const key of ["agent_id", "agent_version_id", "provider", "model"]) workspaceParams.delete(key);
    window.history.replaceState(null, "", `${window.location.pathname}${workspaceParams.size ? `?${workspaceParams}` : ""}`);
    void fetchMonitoringOptions(workspaceId, controller.signal).then((result) => {
      setAgents(result.agents.map((agent) => ({ value: agent.id, label: agent.name })));
      setModels(result.models.map((model) => ({ value: `${model.provider}|${model.model}`, label: model.model, secondary: model.provider })));
    }).catch((error: Error) => { if (!controller.signal.aborted) setFailed(error.message); });
    return () => controller.abort();
  }, [workspaceId, readyFromUrl]);

  useEffect(() => {
    if (!filters.agent_id) { setVersions([]); return; }
    const controller = new AbortController();
    void fetchVersions(filters.agent_id).then((items: AgentVersionSummary[]) => {
      if (!controller.signal.aborted) setVersions(items.map((version) => ({ value: version.id, label: `Version ${version.version_number}`, secondary: version.change_note ?? undefined })));
    }).catch(() => { if (!controller.signal.aborted) setVersions([]); });
    return () => controller.abort();
  }, [filters.agent_id]);

  const load = useCallback(async (signal: AbortSignal) => {
    if (!workspaceId || !readyFromUrl) return;
    setLoading(true); setFailed("");
    try {
      const [nextSummary, ...charts] = await Promise.all([
        fetchMonitoringSummary(workspaceId, applied, signal),
        ...metricDefinitions.map((metric) => fetchMonitoringSeries(workspaceId, metric.key, applied, signal)),
      ]);
      if (signal.aborted) return;
      const nextSeries: Record<string, MonitoringSeries> = {};
      metricDefinitions.forEach((metric, index) => { nextSeries[metric.key] = charts[index]; });
      setSummary(nextSummary); setSeries(nextSeries); setUpdatedAt(new Date().toLocaleTimeString());
    } catch (error) {
      if (!signal.aborted) setFailed(error instanceof Error ? error.message : "Could not load monitoring data.");
    } finally { if (!signal.aborted) setLoading(false); }
  }, [workspaceId, readyFromUrl, applied]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, refreshKey]);

  function setPresetRange(value: string) {
    setPreset(value);
    const end = new Date();
    const start = new Date(end.getTime() - (value === "24h" ? 86_400_000 : value === "30d" ? 30 * 86_400_000 : 7 * 86_400_000));
    setFilters((current) => ({ ...current, from: start.toISOString(), to: end.toISOString() }));
  }

  function applyFilters() {
    const start = new Date(filters.from).getTime(); const end = new Date(filters.to).getTime();
    if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end || end - start > 90 * 86_400_000) { setValidationError("Choose a valid period of up to 90 days."); return; }
    setValidationError("");
    const next = { ...filters, from: new Date(start).toISOString(), to: new Date(end).toISOString() };
    setFilters(next); setApplied(next);
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(next)) if (value) params.set(key, value);
    window.history.pushState(null, "", `${window.location.pathname}?${params}`);
  }

  const agentOptions = useMemo(() => [{ value: "", label: "All agents" }, ...agents], [agents]);
  const versionOptions = useMemo(() => [{ value: "", label: "All versions" }, ...versions], [versions]);
  const modelOptions = useMemo(() => [{ value: "", label: "All models" }, ...models], [models]);
  const statusOptions: PrimarySelectOption[] = [{ value: "", label: "All statuses" }, ...["COMPLETED", "FAILED", "CANCELLED", "RUNNING", "QUEUED", "WAITING_TOOL", "WAITING_APPROVAL"].map((status) => ({ value: status, label: status.replaceAll("_", " ") }))];
  const modelValue = filters.provider && filters.model ? `${filters.provider}|${filters.model}` : "";

  function update(key: keyof MonitoringFilters, value: string) {
    setFilters((current) => key === "agent_id" ? { ...current, agent_id: value, agent_version_id: "" } : key === "provider" ? { ...current, provider: value.split("|")[0] ?? "", model: value.split("|")[1] ?? "" } : { ...current, [key]: value });
  }

  return <div className="monitoring-page">
    <header className="page-header monitoring-page-header"><div><p className="eyebrow">VibesFactory / Observe</p><h1>Monitoring</h1><p className="page-description">Understand agent reliability, latency, usage and estimated model cost.</p></div><div className="monitoring-refresh-area"><button className="button secondary-button monitoring-refresh" type="button" disabled={loading || !workspaceId} onClick={() => setRefreshKey((key) => key + 1)}><RefreshCw size={15} className={loading ? "monitoring-spin" : ""} aria-hidden="true" />Refresh</button><small>{updatedAt ? `Updated ${updatedAt}` : loading ? "Loading workspace data…" : "Waiting for workspace"}</small></div></header>
    <section className="panel monitoring-filters" aria-label="Monitoring filters"><div className="monitoring-filter-row">
      <label className="monitoring-filter-field"><span>Time range</span><PrimarySelect value={preset} options={[{ value: "24h", label: "Last 24 hours" }, { value: "7d", label: "Last 7 days" }, { value: "30d", label: "Last 30 days" }, { value: "custom", label: "Custom range" }]} placeholder="Choose range" ariaLabel="Time range" onChange={setPresetRange} /></label>
      <label className="monitoring-filter-field"><span>Agent</span><PrimarySelect value={filters.agent_id} options={agentOptions} placeholder="All agents" ariaLabel="Agent" searchable searchPlaceholder="Search agents…" onChange={(value) => update("agent_id", value)} /></label>
      <label className="monitoring-filter-field"><span>Version</span><PrimarySelect value={filters.agent_version_id} options={versionOptions} placeholder="All versions" ariaLabel="Agent version" disabled={!filters.agent_id} onChange={(value) => update("agent_version_id", value)} /></label>
      <label className="monitoring-filter-field"><span>Provider / model</span><PrimarySelect value={modelValue} options={modelOptions} placeholder="All models" ariaLabel="Provider and model" searchable searchPlaceholder="Search providers and models…" onChange={(value) => update("provider", value)} /></label>
      <label className="monitoring-filter-field"><span>Status</span><PrimarySelect value={filters.status} options={statusOptions} placeholder="All statuses" ariaLabel="Run status" onChange={(value) => update("status", value)} /></label>
    </div>
    {preset === "custom" ? <div className="monitoring-custom-range"><label className="monitoring-filter-field"><span>From</span><PrimaryTextInput type="datetime-local" value={toLocalInput(new Date(filters.from))} onChange={(event) => { if (event.target.value) update("from", new Date(event.target.value).toISOString()); }} /></label><label className="monitoring-filter-field"><span>To</span><PrimaryTextInput type="datetime-local" value={toLocalInput(new Date(filters.to))} onChange={(event) => { if (event.target.value) update("to", new Date(event.target.value).toISOString()); }} /></label></div> : null}
    <div className="monitoring-filter-footer">{validationError ? <span className="monitoring-inline-error" role="alert">{validationError}</span> : <span>Evaluation runs are excluded.</span>}<div><button className="button secondary-button" type="button" onClick={() => { const next = defaultFilters(); setFilters(next); setApplied(next); setPreset("7d"); window.history.pushState(null, "", window.location.pathname); }}>Reset</button><button className="button primary-button" type="button" disabled={loading} onClick={applyFilters}>Apply filters</button></div></div></section>
    {failed ? <div className={summary ? "monitoring-alert stale" : "monitoring-alert error"} role="alert"><AlertTriangle size={16} aria-hidden="true"/><span><strong>{summary ? "Showing the last successful snapshot." : "Monitoring data could not be loaded."}</strong> {failed}{summary ? " Refresh to try again." : " Use Refresh to retry."}</span></div> : null}
    {!workspaceId ? <div className="empty-state-panel">Choose a workspace to view monitoring data.</div> : loading && !summary ? <section className="monitoring-skeleton" aria-label="Loading monitoring data"><i/><i/><i/><i/></section> : null}
    {summary ? <>
      <section className="monitoring-kpi-grid" aria-label="Workspace monitoring metrics">
        <MetricCard label="Total runs" value={integer(summary.runs.total)} detail={`${integer(summary.runs.completed)} completed · ${integer(summary.runs.failed)} failed`} icon={Activity} tone="purple" />
        <MetricCard label="Success rate" value={percent(summary.runs.success_rate)} detail={`${integer(summary.runs.in_progress)} in progress · ${integer(summary.runs.cancelled)} cancelled`} icon={Workflow} tone="blue" />
        <MetricCard label="Average latency" value={duration(summary.latency.average_ms)} detail={`P95 ${duration(summary.latency.p95_ms)}`} icon={Timer} tone="cyan" />
        <MetricCard label="Estimated cost · USD" value={money(summary.estimated_cost)} detail={`${integer(summary.data_quality.accounted_runs)} of ${integer(summary.runs.total)} runs accounted`} icon={CircleDollarSign} tone="green" />
      </section>
      <section className="monitoring-secondary-metrics" aria-label="Additional metrics"><div><span>Failure rate</span><strong>{percent(summary.runs.failure_rate)}</strong></div><div><span>Model latency</span><strong>{duration(summary.model_latency.average_ms)}</strong></div><div><span>Input tokens</span><strong>{integer(summary.usage.input_tokens)}{summary.data_quality.estimated_input_calls ? " est." : ""}</strong></div><div><span>Output tokens</span><strong>{integer(summary.usage.output_tokens)}{summary.data_quality.estimated_output_calls ? " est." : ""}</strong></div><div><span>Tool failures</span><strong>{integer(summary.tool_failures.count)} · {percent(summary.tool_failures.rate)}</strong></div></section>
      {!summary.data_quality.cost_complete ? <div className="monitoring-alert stale" role="status"><AlertTriangle size={16} aria-hidden="true"/><span>Cost coverage is partial. {integer(summary.data_quality.legacy_runs)} historical runs and {integer(summary.data_quality.missing_pricing_or_usage_calls)} model calls have incomplete accounting. Costs shown are estimates, not provider billing.</span></div> : <p className="monitoring-cost-note">Estimated cost uses the pricing registered for each model call. It is not provider billing.</p>}
      <section className="monitoring-chart-grid" aria-label="Usage over time">{metricDefinitions.map((metric) => <TimeSeriesChart key={metric.key} title={metric.title} color={metric.color} format={metric.format} series={series[metric.key]} />)}</section>
    </> : null}
    {summary && summary.runs.total === 0 ? <div className="monitoring-empty" role="status"><Activity size={20} aria-hidden="true"/><div><strong>No runs in this period</strong><span>Adjust the time range or clear filters to view activity.</span></div></div> : null}
  </div>;
}

export default function MonitoringPage() { return <AppShell><MonitoringContent /></AppShell>; }
