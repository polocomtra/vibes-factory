"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  Check,
  ChevronDown,
  CircleDollarSign,
  Cloud,
  ExternalLink,
  GitBranch,
  MoreHorizontal,
  Plus,
  Sparkles,
  Timer,
  Workflow,
} from "lucide-react";

import { AppShell } from "../components/app-shell";

const stats = [
  { label: "Total agents", value: "12", delta: "21%", caption: "vs last week", trend: "up", icon: Bot, tone: "purple" },
  { label: "Total runs", value: "1,482", delta: "12%", caption: "vs last week", trend: "up", icon: Sparkles, tone: "blue" },
  { label: "Success rate", value: "96.4%", delta: "1.3%", caption: "vs last week", trend: "up", icon: Check, tone: "green" },
  { label: "Estimated cost", value: "$24.32", delta: "18%", caption: "vs last week", trend: "down", icon: CircleDollarSign, tone: "pink" },
];

const recentRuns = [
  { name: "Customer Support Agent", type: "Agent run", time: "2m ago", status: "Completed", tone: "success" },
  { name: "Research Assistant", type: "Agent run", time: "5m ago", status: "Completed", tone: "success" },
  { name: "Content Generator", type: "Workflow run", time: "12m ago", status: "Failed", tone: "error" },
  { name: "Data Analyst Agent", type: "Agent run", time: "18m ago", status: "Completed", tone: "success" },
  { name: "Marketing Agent", type: "Agent run", time: "1h ago", status: "Completed", tone: "success" },
];

const agents = [
  { name: "Customer Support Agent", initials: "CS", runs: "842", success: "97.1%", latency: "2.3s", cost: "$12.81" },
  { name: "Research Assistant", initials: "RA", runs: "321", success: "95.6%", latency: "5.1s", cost: "$6.21" },
  { name: "Content Generator", initials: "CG", runs: "198", success: "93.4%", latency: "6.8s", cost: "$4.12" },
];

function PageHeader() {
  return (
    <div className="page-header">
      <div>
        <p className="eyebrow">VibesFactory / Control plane</p>
        <h1>Dashboard</h1>
        <p className="page-description">Welcome back. Here’s what’s happening in your workspace.</p>
      </div>
      <div className="header-controls">
        <button className="select-button" type="button">Last 7 days <ChevronDown size={15} aria-hidden="true" /></button>
        <button className="button primary-button" type="button"><Plus size={16} aria-hidden="true" />New agent</button>
      </div>
    </div>
  );
}

function MetricCard({ stat }: { stat: (typeof stats)[number] }) {
  const Icon = stat.icon;
  return (
    <article className={`metric-card metric-${stat.tone}`}>
      <div className="metric-topline"><span className="metric-label">{stat.label}</span><span className="metric-icon"><Icon size={16} aria-hidden="true" /></span></div>
      <strong className="metric-value">{stat.value}</strong>
      <div className="metric-footer"><span className={stat.trend === "up" ? "delta positive" : "delta negative"}>{stat.trend === "up" ? <ArrowUpRight size={14} aria-hidden="true" /> : <ArrowDownRight size={14} aria-hidden="true" />}{stat.delta}</span><span>{stat.caption}</span></div>
    </article>
  );
}

function RunsChart() {
  return (
    <article className="panel chart-panel">
      <div className="panel-heading"><div><span className="panel-kicker">Runtime activity</span><h2>Runs over time</h2></div><button className="text-button" type="button">View details <ArrowUpRight size={14} aria-hidden="true" /></button></div>
      <div className="chart-legend"><span className="legend-line" /> Runs <span className="legend-note">Last 7 days</span></div>
      <div className="chart-wrap">
        <div className="y-axis"><span>400</span><span>300</span><span>200</span><span>100</span><span>0</span></div>
        <div className="chart-area" aria-label="Runs increased from 140 to 324 over the last seven days" role="img">
          <div className="chart-grid-lines"><i /><i /><i /><i /><i /></div>
          <svg className="run-line" viewBox="0 0 640 220" preserveAspectRatio="none" aria-hidden="true">
            <defs><linearGradient id="run-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="var(--chart-fill)" stopOpacity="0.34" /><stop offset="100%" stopColor="var(--chart-fill)" stopOpacity="0" /></linearGradient><filter id="line-glow"><feGaussianBlur stdDeviation="4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
            <path className="area-path" d="M0 156 L53 139 L107 147 L160 116 L213 130 L267 87 L320 110 L373 86 L427 72 L480 91 L533 77 L587 86 L640 38 L640 220 L0 220 Z" />
            <path className="line-path" d="M0 156 L53 139 L107 147 L160 116 L213 130 L267 87 L320 110 L373 86 L427 72 L480 91 L533 77 L587 86 L640 38" filter="url(#line-glow)" /><circle className="chart-point" cx="427" cy="72" r="5" />
          </svg>
          <div className="chart-tooltip"><strong>324 runs</strong><span>+23% vs last week</span></div>
          <div className="x-axis"><span>Nov 10</span><span>Nov 11</span><span>Nov 12</span><span>Nov 13</span><span>Nov 14</span><span>Nov 15</span><span>Nov 16</span></div>
        </div>
      </div>
    </article>
  );
}

function RecentRuns() {
  return (
    <article className="panel recent-panel">
      <div className="panel-heading"><div><span className="panel-kicker">Latest activity</span><h2>Recent runs</h2></div><button className="text-button" type="button">View all <ArrowUpRight size={14} aria-hidden="true" /></button></div>
      <div className="run-list">{recentRuns.map((run) => <button className="run-row" type="button" key={run.name}><span className={`run-status-dot ${run.tone}`} aria-hidden="true" /><span className="run-row-copy"><strong>{run.name}</strong><small>{run.type}</small></span><span className="run-row-meta"><b className={run.tone}>{run.status}</b><small>{run.time}</small></span></button>)}</div>
    </article>
  );
}

function AgentUsage() {
  return (
    <article className="panel table-panel">
      <div className="panel-heading"><div><span className="panel-kicker">Workspace performance</span><h2>Top agents by usage</h2></div><button className="icon-button subtle" type="button" aria-label="More agent usage options"><MoreHorizontal size={17} aria-hidden="true" /></button></div>
      <div className="table-scroll"><table><thead><tr><th>Agent</th><th>Runs</th><th>Success rate</th><th>Avg. latency</th><th>Cost</th></tr></thead><tbody>{agents.map((agent) => <tr key={agent.name}><td><span className="agent-name"><span className="agent-avatar">{agent.initials}</span><strong>{agent.name}</strong></span></td><td>{agent.runs}</td><td className="success-text">{agent.success}</td><td>{agent.latency}</td><td>{agent.cost}</td></tr>)}</tbody></table></div>
    </article>
  );
}

function CapabilityCard() {
  return (
    <article className="panel capability-panel">
      <div className="panel-heading"><div><span className="panel-kicker">Build surface</span><h2>Platform capabilities</h2></div><span className="coverage-value">64%</span></div>
      <div className="coverage-track"><span /></div><p className="panel-copy">Your workspace is ready to connect knowledge, tools and workflows to your agents.</p>
      <div className="capability-list"><span><Bot size={15} aria-hidden="true" /> Agents <b>12</b></span><span><Workflow size={15} aria-hidden="true" /> Workflows <b>4</b></span><span><Timer size={15} aria-hidden="true" /> Evaluations <b>8</b></span></div>
      <button className="button secondary-button full-button" type="button">Explore workspace <ArrowUpRight size={15} aria-hidden="true" /></button>
    </article>
  );
}

function DeploymentsCard() {
  return (
    <article className="panel deployments-panel">
      <div className="panel-heading"><div><span className="panel-kicker">Runtime endpoints</span><h2>Deployments</h2></div><button className="text-button" type="button">Manage <ArrowUpRight size={14} aria-hidden="true" /></button></div>
      <div className="deployment-list"><div className="deployment-row"><span className="deployment-icon production"><Cloud size={16} aria-hidden="true" /></span><span><strong>Production</strong><small>Customer Support Agent · v1.3.0</small></span><b className="status-badge success"><span />Healthy</b></div><div className="deployment-row"><span className="deployment-icon staging"><GitBranch size={16} aria-hidden="true" /></span><span><strong>Staging</strong><small>Research Assistant · v0.8.1-rc1</small></span><b className="status-badge info"><span />Deploying</b></div></div>
    </article>
  );
}

export default function DashboardPage() {
  return (
    <AppShell>
      <PageHeader />
      <section className="metric-grid" aria-label="Workspace metrics">{stats.map((stat) => <MetricCard key={stat.label} stat={stat} />)}</section>
      <section className="dashboard-grid primary-grid"><RunsChart /><RecentRuns /></section>
      <section className="dashboard-grid secondary-grid"><AgentUsage /><CapabilityCard /><DeploymentsCard /></section>
      <footer className="app-footer"><span><span className="status-pulse" /> VibesFactory API · v0.1.0</span><span className="footer-links"><a href="#docs">Docs</a><a href="#status">Status</a><a href="#support">Support</a></span></footer>
    </AppShell>
  );
}
