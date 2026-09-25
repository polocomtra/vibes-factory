"use client";

import {
    Bot,
    CalendarDays,
    Check,
    CircleAlert,
    Grid2X2,
    List,
    LoaderCircle,
    RotateCcw,
    Search,
    SlidersHorizontal,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "../../components/app-shell";
import { PaginationControls } from "../../components/pagination-controls";
import { fetchTraces, type TraceListItem } from "../../lib/runtime";

type LayoutMode = "grid" | "list";
type TimeRange = "all" | "24h" | "7d" | "30d";
type TraceSessionItem = Omit<TraceListItem, "input_text"> & {
    first_user_message: string | null;
    latest_user_message: string | null;
    trace_count: number;
};

function dateLabel(value: string) {
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(value));
}

function durationLabel(value: number | null) {
    if (value === null) return "—";
    if (value < 1000) return `${value} ms`;
    return `${(value / 1000).toFixed(1)} s`;
}

function shortId(value: string | null, length: number) {
    return value ? `${value.slice(0, length)}…` : "—";
}

function traceSubject(trace: TraceSessionItem) {
    return trace.agent_name || "Workflow execution";
}

function traceRunLabel(trace: TraceSessionItem) {
    if (trace.run_id) return `Run ${shortId(trace.run_id, 10)}`;
    if (trace.workflow_run_id)
        return `Workflow run ${shortId(trace.workflow_run_id, 10)}`;
    return `Trace ${shortId(trace.id, 10)}`;
}

function statusTone(status: TraceListItem["status"]) {
    return status === "COMPLETED"
        ? "success"
        : status === "FAILED"
          ? "error"
          : "info";
}

function TraceStatus({ status }: { status: TraceListItem["status"] }) {
    return (
        <span className={`status-badge ${statusTone(status)}`}>
            <span aria-hidden="true" />
            {status.replaceAll("_", " ")}
        </span>
    );
}

function rangeStart(range: TimeRange) {
    if (range === "all") return undefined;
    const start = new Date();
    start.setHours(
        start.getHours() -
            (range === "24h" ? 24 : range === "7d" ? 24 * 7 : 24 * 30),
    );
    return start.toISOString();
}

function TracePreview({ trace }: { trace: TraceSessionItem }) {
    const hasDifferentMessages =
        trace.first_user_message !== trace.latest_user_message;
    return (
        <div className="trace-message-summary">
            <div>
                <small>First user message</small>
                <p>{trace.first_user_message || "No input recorded."}</p>
            </div>
            {hasDifferentMessages ? (
                <div>
                    <small>Latest user message</small>
                    <p>{trace.latest_user_message || "No input recorded."}</p>
                </div>
            ) : null}
        </div>
    );
}

function TraceGridCard({
    trace,
    onOpenTrace,
}: {
    trace: TraceSessionItem;
    onOpenTrace: (trace: TraceSessionItem) => void;
}) {
    return (
        <article className="trace-card">
            <div className="trace-card-topline">
                <span className="trace-agent-mark">
                    <Bot size={15} aria-hidden="true" />
                </span>
                <TraceStatus status={trace.status} />
            </div>
            <div className="trace-card-heading">
                <div>
                    <h2>{traceSubject(trace)}</h2>
                    <p>
                        {trace.trace_count}{" "}
                        {trace.trace_count === 1 ? "run" : "runs"} ·{" "}
                        <code>{traceRunLabel(trace)}</code>
                    </p>
                </div>
                <span className="trace-duration">
                    {durationLabel(trace.duration_ms)}
                </span>
            </div>
            <TracePreview trace={trace} />
            <div className="trace-card-meta">
                <span>
                    <small>Latest activity</small>
                    <b>{dateLabel(trace.started_at)}</b>
                </span>
                <span>
                    <small>Version ID</small>
                    <b>
                        {trace.agent_version_id
                            ? shortId(trace.agent_version_id, 8)
                            : "Workflow trace"}
                    </b>
                </span>
            </div>
            <footer>
                <code>
                    {trace.session_id
                        ? `Session ${trace.session_id}`
                        : trace.workflow_run_id
                          ? `Workflow run ${trace.workflow_run_id}`
                          : `Trace ${trace.id}`}
                </code>
                {trace.session_id ? (
                    <button
                        className="text-button"
                        type="button"
                        onClick={() => onOpenTrace(trace)}
                    >
                        Open session <span aria-hidden="true">→</span>
                    </button>
                ) : trace.workflow_id ? (
                    <button
                        className="text-button trace-workflow-open-button"
                        type="button"
                        onClick={() => onOpenTrace(trace)}
                    >
                        Open workflow<span aria-hidden="true">→</span>
                    </button>
                ) : (
                    <span className="trace-no-session">No session</span>
                )}
            </footer>
        </article>
    );
}

function TraceListRow({
    trace,
    onOpenTrace,
}: {
    trace: TraceSessionItem;
    onOpenTrace: (trace: TraceSessionItem) => void;
}) {
    return (
        <article className="trace-list-row">
            <div className="trace-list-agent">
                <span className="trace-agent-mark">
                    <Bot size={15} aria-hidden="true" />
                </span>
                <span>
                    <strong>{traceSubject(trace)}</strong>
                    <small>
                        {trace.trace_count}{" "}
                        {trace.trace_count === 1 ? "run" : "runs"} ·{" "}
                        <code>{traceRunLabel(trace)}</code>
                    </small>
                </span>
            </div>
            <TraceStatus status={trace.status} />
            <span className="trace-list-time">
                <CalendarDays size={14} aria-hidden="true" />
                {dateLabel(trace.started_at)}
            </span>
            <span className="trace-list-duration">
                {durationLabel(trace.duration_ms)}
            </span>
            <code className="trace-list-id">
                {trace.session_id
                    ? trace.session_id.slice(0, 12)
                    : trace.id.slice(0, 12)}
                …
            </code>
            {trace.session_id ? (
                <button
                    className="button secondary-button trace-open-button"
                    type="button"
                    onClick={() => onOpenTrace(trace)}
                >
                    Open session
                </button>
            ) : trace.workflow_id ? (
                <button
                    className="button secondary-button trace-open-button trace-workflow-open-button"
                    type="button"
                    onClick={() => onOpenTrace(trace)}
                >
                    Open to Workflow Run History
                </button>
            ) : (
                <span className="trace-no-session">No session</span>
            )}
        </article>
    );
}

function groupTracesBySession(traces: TraceListItem[]): TraceSessionItem[] {
    const groups = new Map<string, TraceSessionItem>();
    const chronological = [...traces].sort(
        (left, right) =>
            Date.parse(left.started_at) - Date.parse(right.started_at),
    );
    for (const trace of chronological) {
        const key = trace.session_id ?? `trace:${trace.id}`;
        const existing = groups.get(key);
        if (!existing) {
            const { input_text, ...latestTrace } = trace;
            groups.set(key, {
                ...latestTrace,
                first_user_message: input_text,
                latest_user_message: input_text,
                trace_count: 1,
            });
            continue;
        }
        existing.trace_count += 1;
        if (!existing.first_user_message && trace.input_text)
            existing.first_user_message = trace.input_text;
        if (trace.input_text) existing.latest_user_message = trace.input_text;
        if (Date.parse(trace.started_at) >= Date.parse(existing.started_at)) {
            const { input_text: _inputText, ...latestTrace } = trace;
            Object.assign(existing, latestTrace);
        }
    }
    return [...groups.values()].sort(
        (left, right) =>
            Date.parse(right.started_at) - Date.parse(left.started_at),
    );
}

export default function TracesPage() {
    const router = useRouter();
    const [traces, setTraces] = useState<TraceListItem[]>([]);
    const [agentSearch, setAgentSearch] = useState("");
    const [status, setStatus] = useState("");
    const [timeRange, setTimeRange] = useState<TimeRange>("all");
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(6);
    const [layout, setLayout] = useState<LayoutMode>("grid");
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const sessionItems = useMemo(() => groupTracesBySession(traces), [traces]);

    useEffect(() => {
        let cancelled = false;
        setPage(1);
        const timer = window.setTimeout(
            () => {
                setLoading(true);
                setError(null);
                setNextCursor(null);
                void fetchTraces({
                    agent: agentSearch.trim() || undefined,
                    status: status || undefined,
                    started_after: rangeStart(timeRange),
                })
                    .then((page) => {
                        if (!cancelled) {
                            setTraces(page.data);
                            setNextCursor(page.pagination.next_cursor);
                        }
                    })
                    .catch((reason: unknown) => {
                        if (!cancelled)
                            setError(
                                reason instanceof Error
                                    ? reason.message
                                    : "Unable to load traces.",
                            );
                    })
                    .finally(() => {
                        if (!cancelled) setLoading(false);
                    });
            },
            agentSearch ? 260 : 0,
        );
        return () => {
            cancelled = true;
            window.clearTimeout(timer);
        };
    }, [agentSearch, status, timeRange]);

    const totalPages = Math.max(1, Math.ceil(sessionItems.length / pageSize));
    const currentPage = Math.min(page, totalPages);
    const visibleSessionItems = sessionItems.slice(
        (currentPage - 1) * pageSize,
        currentPage * pageSize,
    );

    async function loadMore() {
        if (!nextCursor || loadingMore) return;
        setLoadingMore(true);
        setError(null);
        try {
            const page = await fetchTraces(
                {
                    agent: agentSearch.trim() || undefined,
                    status: status || undefined,
                    started_after: rangeStart(timeRange),
                },
                nextCursor,
            );
            setTraces((items) => [...items, ...page.data]);
            setNextCursor(page.pagination.next_cursor);
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Unable to load more traces.",
            );
        } finally {
            setLoadingMore(false);
        }
    }

    const summary = useMemo(
        () => ({
            total: sessionItems.length,
            completed: sessionItems.filter(
                (trace) => trace.status === "COMPLETED",
            ).length,
            failed: sessionItems.filter((trace) => trace.status === "FAILED")
                .length,
        }),
        [sessionItems],
    );

    function clearFilters() {
        setAgentSearch("");
        setStatus("");
        setTimeRange("all");
    }

    function openTrace(trace: TraceSessionItem) {
        if (trace.session_id && trace.agent_id)
            router.push(
                `/agents/${trace.agent_id}/playground?session_id=${trace.session_id}`,
            );
        else if (trace.workflow_id)
            router.push(`/workflows/${trace.workflow_id}/runs`);
    }

    return (
        <AppShell>
            <div className="pagination-page traces-page">
                <div className="page-header traces-header">
                    <div>
                        <p className="eyebrow">VibesFactory / Operate</p>
                        <h1>Traces</h1>
                        <p className="page-description">
                            Explore runtime executions across the agents in your
                            workspaces.
                        </p>
                    </div>
                    <div className="traces-header-actions">
                        <span className="traces-count">
                            <strong>{summary.total}</strong> traces
                        </span>
                        <div
                            className="layout-toggle"
                            role="group"
                            aria-label="Trace layout"
                        >
                            <button
                                className={layout === "grid" ? "selected" : ""}
                                type="button"
                                aria-label="Grid view"
                                aria-pressed={layout === "grid"}
                                onClick={() => setLayout("grid")}
                            >
                                <Grid2X2 size={15} aria-hidden="true" />
                            </button>
                            <button
                                className={layout === "list" ? "selected" : ""}
                                type="button"
                                aria-label="List view"
                                aria-pressed={layout === "list"}
                                onClick={() => setLayout("list")}
                            >
                                <List size={15} aria-hidden="true" />
                            </button>
                        </div>
                    </div>
                </div>
                <section
                    className="panel traces-filter-panel"
                    aria-label="Trace filters"
                >
                    <div className="traces-filter-leading">
                        <SlidersHorizontal size={15} aria-hidden="true" />
                        <span>Filter traces</span>
                    </div>
                    <label className="trace-filter-search">
                        <Search size={15} aria-hidden="true" />
                        <span className="sr-only">Search by agent name</span>
                        <input
                            value={agentSearch}
                            onChange={(event) =>
                                setAgentSearch(event.target.value)
                            }
                            placeholder="Search agent name or slug…"
                        />
                    </label>
                    <label className="trace-filter-select">
                        <span>Status</span>
                        <select
                            value={status}
                            onChange={(event) => setStatus(event.target.value)}
                        >
                            <option value="">All statuses</option>
                            <option value="COMPLETED">Completed</option>
                            <option value="FAILED">Failed</option>
                            <option value="RUNNING">Running</option>
                        </select>
                    </label>
                    <label className="trace-filter-select">
                        <span>Time range</span>
                        <select
                            value={timeRange}
                            onChange={(event) =>
                                setTimeRange(event.target.value as TimeRange)
                            }
                        >
                            <option value="all">Any time</option>
                            <option value="24h">Last 24 hours</option>
                            <option value="7d">Last 7 days</option>
                            <option value="30d">Last 30 days</option>
                        </select>
                    </label>
                    <button
                        className="button secondary-button trace-reset-button"
                        type="button"
                        onClick={clearFilters}
                        disabled={
                            !agentSearch && !status && timeRange === "all"
                        }
                    >
                        <RotateCcw size={14} aria-hidden="true" />
                        Reset
                    </button>
                </section>
                {error ? (
                    <div className="form-error traces-alert" role="alert">
                        <CircleAlert size={15} aria-hidden="true" />
                        {error}
                        <button
                            className="text-button"
                            type="button"
                            onClick={clearFilters}
                        >
                            Clear filters
                        </button>
                    </div>
                ) : null}
                <div className="traces-summary" aria-live="polite">
                    <span>
                        {loading
                            ? "Loading traces…"
                            : `${summary.total} visible traces`}
                    </span>
                    <span>
                        {summary.completed} latest completed · {summary.failed}{" "}
                        latest failed
                    </span>
                </div>
                {loading ? (
                    <section className="panel agent-state">
                        <LoaderCircle
                            className="spin"
                            size={18}
                            aria-hidden="true"
                        />
                        Loading traces…
                    </section>
                ) : sessionItems.length === 0 ? (
                    <section className="panel agent-empty-state traces-empty">
                        <Search size={28} aria-hidden="true" />
                        <h2>No traces found</h2>
                        <p className="panel-copy">
                            Try a different agent, status, or time range.
                        </p>
                        <button
                            className="button secondary-button"
                            type="button"
                            onClick={clearFilters}
                        >
                            Reset filters
                        </button>
                    </section>
                ) : (
                    <>
                        {layout === "grid" ? (
                            <section
                                className="traces-grid"
                                aria-label="Trace sessions grid"
                            >
                                {visibleSessionItems.map((trace) => (
                                    <TraceGridCard
                                        key={trace.session_id ?? trace.id}
                                        trace={trace}
                                        onOpenTrace={openTrace}
                                    />
                                ))}
                            </section>
                        ) : (
                            <section
                                className="traces-list"
                                aria-label="Trace sessions list"
                            >
                                {visibleSessionItems.map((trace) => (
                                    <TraceListRow
                                        key={trace.session_id ?? trace.id}
                                        trace={trace}
                                        onOpenTrace={openTrace}
                                    />
                                ))}
                            </section>
                        )}
                        {nextCursor ? (
                            <div className="traces-load-more">
                                <button
                                    className="button secondary-button"
                                    type="button"
                                    onClick={() => void loadMore()}
                                    disabled={loadingMore}
                                >
                                    {loadingMore ? (
                                        <LoaderCircle
                                            className="spin"
                                            size={14}
                                            aria-hidden="true"
                                        />
                                    ) : null}
                                    {loadingMore
                                        ? "Loading…"
                                        : "Load more traces"}
                                </button>
                            </div>
                        ) : null}
                        <PaginationControls
                            page={currentPage}
                            pageSize={pageSize}
                            totalItems={sessionItems.length}
                            onPageChange={setPage}
                            onPageSizeChange={setPageSize}
                            ariaLabel="Traces pagination"
                        />
                    </>
                )}
            </div>
        </AppShell>
    );
}
