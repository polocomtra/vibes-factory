"use client";

import { Activity, ArrowRight, CircleDollarSign, Timer, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import Link from "next/link";

import { AppShell, useSelectedWorkspaceId, useWorkspaceLoadStatus } from "../components/app-shell";
import { fetchMonitoringSeries, fetchMonitoringSummary, type MonitoringFilters, type MonitoringSeries, type MonitoringSummary } from "../lib/monitoring";

function integer(value: number | null | undefined) { return value == null ? "—" : new Intl.NumberFormat().format(value); }
function percent(value: number | null | undefined) { return value == null ? "—" : `${(value * 100).toFixed(1)}%`; }
function duration(value: number | null | undefined) { return value == null ? "—" : value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`; }
function money(value: number | string | null | undefined) { return value == null ? "—" : new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 4 }).format(Number(value)); }
function defaultFilters(): MonitoringFilters {
  const to = new Date();
  const from = new Date(to.getTime() - 7 * 86_400_000);
  return { from: from.toISOString(), to: to.toISOString(), agent_id: "", agent_version_id: "", provider: "", model: "", status: "" };
}

function Metric({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: typeof Activity }) {
  return <article className="dashboard-v2-metric"><span className="dashboard-v2-metric-icon"><Icon size={17} aria-hidden="true" /></span><span className="dashboard-v2-metric-label">{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function ActivitySeries({ series }: { series: MonitoringSeries | null }) {
  const values = series?.points.map((point) => point.value) ?? [];
  const max = Math.max(...values.filter((value): value is number => value != null), 1);
  return <section className="panel dashboard-v2-series">
    <div className="panel-heading"><div><span className="panel-kicker">Last 7 days</span><h2>Runtime activity</h2></div><Link className="text-button" href="/monitoring">Open Monitoring <ArrowRight size={15} aria-hidden="true" /></Link></div>
    {!series || series.points.length === 0 ? <p className="dashboard-v2-muted">No time-series data is available for this period.</p> : <>
      <ol className="dashboard-v2-bars" aria-label="Run volume by interval">
        {series.points.map((point, index) => <li key={`${point.timestamp}-${index}`} title={`${new Date(point.timestamp).toLocaleString()}: ${point.value == null ? "No data" : integer(point.value)} runs`}><span className={point.value == null ? "dashboard-v2-bar missing" : "dashboard-v2-bar"} style={{ height: point.value == null ? "8px" : `${Math.max(6, (point.value / max) * 100)}%` }} aria-hidden="true" /><span className="sr-only">{new Date(point.timestamp).toLocaleString()}: {point.value == null ? "No data" : `${integer(point.value)} runs`}</span></li>)}
      </ol>
      <details className="dashboard-v2-data"><summary>View activity data</summary><div className="table-scroll"><table><thead><tr><th scope="col">Time</th><th scope="col">Runs</th><th scope="col">Data quality</th></tr></thead><tbody>{series.points.map((point, index) => <tr key={`${point.timestamp}-table-${index}`}><td>{new Date(point.timestamp).toLocaleString()}</td><td>{integer(point.value)}</td><td>{point.complete ? "Complete" : point.value == null ? "No data" : "Partial"}</td></tr>)}</tbody></table></div></details>
    </>}
  </section>;
}

function DashboardContent() {
  const workspaceId = useSelectedWorkspaceId();
  const workspaceStatus = useWorkspaceLoadStatus();
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [series, setSeries] = useState<MonitoringSeries | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => {
    if (!workspaceId) { setLoading(false); setSummary(null); setSeries(null); return; }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setSummary(null);
    setSeries(null);
    const filters = defaultFilters();
    void Promise.allSettled([
      fetchMonitoringSummary(workspaceId, filters, controller.signal),
      fetchMonitoringSeries(workspaceId, "runs", filters, controller.signal),
    ]).then(([summaryResult, seriesResult]) => {
      if (controller.signal.aborted) return;
      if (summaryResult.status === "fulfilled") setSummary(summaryResult.value);
      else setError(summaryResult.reason instanceof Error ? summaryResult.reason.message : "Dashboard data could not be loaded.");
      if (seriesResult.status === "fulfilled") setSeries(seriesResult.value);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [workspaceId, refreshKey]);

  return <div className="dashboard-v2">
    <header className="page-header dashboard-v2-header"><div><p className="eyebrow">VibesFactory / Workspace</p><h1>Dashboard</h1><p className="page-description">A clear view of runtime activity and workspace health.</p></div><Link className="button secondary-button" href="/agents">Explore agents <ArrowRight size={15} aria-hidden="true" /></Link></header>
    {error ? <div className="form-error dashboard-v2-error" role="alert"><span>{error}</span><button className="text-button" type="button" onClick={() => setRefreshKey((key) => key + 1)}>Retry</button></div> : null}
    {!workspaceId && workspaceStatus === "loading" ? <section className="panel dashboard-v2-state" role="status"><h2>Loading workspace</h2><p>Workspace activity will appear here when your account is ready.</p></section> : null}
    {!workspaceId && workspaceStatus === "error" ? <section className="panel dashboard-v2-state" role="alert"><h2>Workspace unavailable</h2><p>We could not load workspace information. Reload the page to retry.</p></section> : null}
    {!workspaceId && workspaceStatus === "ready" ? <section className="panel dashboard-v2-state" role="status"><h2>Select a workspace</h2><p>Choose a workspace from the sidebar to see its runtime activity.</p></section> : loading && !summary ? <section className="dashboard-v2-metrics" aria-label="Loading dashboard metrics"><div className="dashboard-v2-skeleton" /><div className="dashboard-v2-skeleton" /><div className="dashboard-v2-skeleton" /><div className="dashboard-v2-skeleton" /></section> : null}
    {summary ? <>
      <section className="dashboard-v2-metrics" aria-label="Runtime metrics for the last seven days">
        <Metric label="Total runs" value={integer(summary.runs.total)} detail={`${integer(summary.runs.completed)} completed · ${integer(summary.runs.failed)} failed`} icon={Activity} />
        <Metric label="Success rate" value={percent(summary.runs.success_rate)} detail={`${integer(summary.runs.in_progress)} in progress`} icon={Workflow} />
        <Metric label="Average latency" value={duration(summary.latency.average_ms)} detail={`P95 ${duration(summary.latency.p95_ms)}`} icon={Timer} />
        <Metric label="Estimated cost · USD" value={money(summary.estimated_cost)} detail={`${integer(summary.data_quality.accounted_runs)} of ${integer(summary.runs.total)} runs accounted`} icon={CircleDollarSign} />
      </section>
      {!summary.data_quality.cost_complete ? <div className="dashboard-v2-note" role="status">Cost coverage is partial. Values are estimates from available usage and configured pricing, not provider billing.</div> : null}
      {summary.runs.total === 0 ? <section className="panel dashboard-v2-state" role="status"><h2>No runs in this period</h2><p>Runtime metrics will appear when an agent or workflow has run.</p><a className="button secondary-button" href="/playground">Open Playground</a></section> : <ActivitySeries series={series} />}
    </> : null}
      <section className="dashboard-v2-shortcuts" aria-label="Workspace areas"><Link href="/workflows"><GitBranchIcon /><span><strong>Workflows</strong><small>Build durable multi-step runs</small></span><ArrowRight size={16} aria-hidden="true" /></Link><Link href="/traces"><Activity size={17} aria-hidden="true" /><span><strong>Traces</strong><small>Inspect sessions, runs, and spans</small></span><ArrowRight size={16} aria-hidden="true" /></Link><Link href="/settings"><Workflow size={17} aria-hidden="true" /><span><strong>Workspace settings</strong><small>Manage membership and connections</small></span><ArrowRight size={16} aria-hidden="true" /></Link></section>
  </div>;
}

function GitBranchIcon() { return <Workflow size={17} aria-hidden="true" />; }

export default function DashboardPage() {
  return <AppShell><DashboardContent /></AppShell>;
}
