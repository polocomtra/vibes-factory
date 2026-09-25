"use client";

import {
    Activity,
    ArrowLeft,
    Bot,
    BookOpen,
    BrainCircuit,
    ChevronDown,
    ChevronRight,
    Clock3,
    FileText,
    GitBranch,
    LoaderCircle,
    Minus,
    Plus,
    Search,
    ShieldCheck,
    Wrench,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { AppShell } from "../../../components/app-shell";
import {
    fetchSpan,
    fetchTraceDetail,
    fetchTraceSpans,
    type Span,
    type TraceDetail,
} from "../../../lib/runtime";

type ViewMode = "timeline" | "tree";
type SpanNode = Span & { children: SpanNode[] };

function formatDuration(value: number | null) {
    if (value === null) return "In progress";
    if (value < 1000) return `${value} ms`;
    if (value < 60_000) return `${(value / 1000).toFixed(2)} s`;
    return `${Math.floor(value / 60_000)}m ${Math.round((value % 60_000) / 1000)}s`;
}

function formatClock(value: number) {
    if (value < 1000) return `${Math.round(value)} ms`;
    return `${(value / 1000).toFixed(1)} s`;
}

function tokenLabel(value: number | undefined) {
    return value === undefined ? "—" : value.toLocaleString();
}

function costLabel(value: string | null | undefined) {
    if (!value || !Number.isFinite(Number(value))) return "—";
    return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 8,
    }).format(Number(value));
}

function timeLabel(value: string) {
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "medium",
    }).format(new Date(value));
}

function statusTone(status: string) {
    return status === "COMPLETED"
        ? "success"
        : status === "FAILED"
          ? "error"
          : "info";
}

function StatusBadge({ status }: { status: string }) {
    return (
        <span className={`status-badge ${statusTone(status)}`}>
            <span aria-hidden="true" />
            {status.replaceAll("_", " ")}
        </span>
    );
}

function spanIcon(type: Span["type"]) {
    switch (type) {
        case "MODEL":
            return Bot;
        case "CONTEXT_BUILD":
            return FileText;
        case "TOOL":
            return Wrench;
        case "RETRIEVAL":
            return BookOpen;
        case "MEMORY_RETRIEVAL":
            return BrainCircuit;
        case "GUARDRAIL":
            return ShieldCheck;
        default:
            return GitBranch;
    }
}

function spanClass(type: Span["type"]) {
    return type.toLowerCase().replaceAll("_", "-");
}

function buildSpanTree(spans: Span[]): SpanNode[] {
    const nodes = new Map<string, SpanNode>();
    for (const span of spans) nodes.set(span.id, { ...span, children: [] });
    const roots: SpanNode[] = [];
    for (const node of nodes.values()) {
        const parent = node.parent_span_id
            ? nodes.get(node.parent_span_id)
            : undefined;
        if (parent && parent.id !== node.id) parent.children.push(node);
        else roots.push(node);
    }
    const sortChildren = (items: SpanNode[]) => {
        items.sort(
            (left, right) =>
                Date.parse(left.started_at) - Date.parse(right.started_at) ||
                left.id.localeCompare(right.id),
        );
        for (const item of items) sortChildren(item.children);
    };
    sortChildren(roots);
    return roots;
}

function flattenVisible(
    nodes: SpanNode[],
    collapsed: Set<string>,
    depth = 0,
): Array<{ node: SpanNode; depth: number }> {
    const rows: Array<{ node: SpanNode; depth: number }> = [];
    for (const node of nodes) {
        rows.push({ node, depth });
        if (!collapsed.has(node.id))
            rows.push(...flattenVisible(node.children, collapsed, depth + 1));
    }
    return rows;
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
    return (
        <section className="trace-detail-section">
            <h3>{title}</h3>
            <pre>{JSON.stringify(value, null, 2)}</pre>
        </section>
    );
}

export default function TraceDetailPage() {
    const params = useParams<{ traceId: string }>();
    const router = useRouter();
    const traceId = params.traceId;
    const [trace, setTrace] = useState<TraceDetail | null>(null);
    const [spans, setSpans] = useState<Span[]>([]);
    const [selected, setSelected] = useState<Span | null>(null);
    const [detail, setDetail] = useState<Span | null>(null);
    const [mode, setMode] = useState<ViewMode>("timeline");
    const [zoom, setZoom] = useState(1);
    const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
    const [loading, setLoading] = useState(true);
    const [spanLoading, setSpanLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [detailError, setDetailError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        void Promise.all([fetchTraceDetail(traceId), fetchTraceSpans(traceId)])
            .then(([traceResult, spanResult]) => {
                if (cancelled) return;
                setTrace(traceResult);
                setSpans(spanResult);
                setSelected(spanResult[0] ?? null);
            })
            .catch((reason: unknown) => {
                if (!cancelled)
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : "Unable to load this trace.",
                    );
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [traceId]);

    useEffect(() => {
        if (!selected) {
            setDetail(null);
            return;
        }
        let cancelled = false;
        setSpanLoading(true);
        setDetailError(null);
        setDetail(selected);
        void fetchSpan(selected.id)
            .then((span) => {
                if (!cancelled) setDetail(span);
            })
            .catch((reason: unknown) => {
                if (!cancelled)
                    setDetailError(
                        reason instanceof Error
                            ? reason.message
                            : "Unable to load span details.",
                    );
            })
            .finally(() => {
                if (!cancelled) setSpanLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [selected]);

    const tree = useMemo(() => buildSpanTree(spans), [spans]);
    const rows = useMemo(
        () => flattenVisible(tree, collapsed),
        [tree, collapsed],
    );
    const timeline = useMemo(() => {
        if (!trace) return { duration: 1 };
        const started = Date.parse(trace.started_at);
        const duration = trace.duration_ms ?? (
            trace.completed_at
                ? Date.parse(trace.completed_at) - started
                : Date.now() - started
        );
        return { duration: Math.max(1, duration) };
    }, [trace]);

    function toggleBranch(id: string) {
        setCollapsed((current) => {
            const next = new Set(current);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }

    function expandAll() {
        setCollapsed(new Set());
    }

    function collapseAll() {
        const parentIds = new Set(
            spans
                .map((span) => span.parent_span_id)
                .filter((parentId): parentId is string => parentId !== null),
        );
        setCollapsed(
            new Set(spans.filter((span) => parentIds.has(span.id)).map((span) => span.id)),
        );
    }

    function selectSpan(span: Span) {
        setSelected(span);
    }

    const selectedDetail = detail ?? selected;
    const SelectedIcon = selectedDetail ? spanIcon(selectedDetail.type) : Activity;
    const traceCost = costLabel(trace?.estimated_cost) === "—"
        ? "Not available"
        : costLabel(trace?.estimated_cost);

    return (
        <AppShell>
            <div className="trace-detail-page">
                <button
                    className="trace-back-link"
                    type="button"
                    onClick={() => router.push("/traces")}
                >
                    <ArrowLeft size={16} aria-hidden="true" />
                    All traces
                </button>
                {loading ? (
                    <section className="panel trace-page-state" aria-live="polite">
                        <LoaderCircle className="spin" size={20} aria-hidden="true" />
                        Loading trace details…
                    </section>
                ) : error ? (
                    <section className="panel trace-page-state trace-page-error" role="alert">
                        <div>
                            <h1>Unable to load trace</h1>
                            <p>{error}</p>
                        </div>
                        <button className="button secondary-button" type="button" onClick={() => window.location.reload()}>
                            Try again
                        </button>
                    </section>
                ) : trace ? (
                    <>
                        <header className="trace-detail-page-header">
                            <div className="trace-detail-title-block">
                                <p className="eyebrow">VibesFactory / Operate / Traces</p>
                                <div className="trace-detail-title-line">
                                    <h1>{trace.agent_name ?? "Workflow trace"}</h1>
                                    <StatusBadge status={trace.status} />
                                </div>
                                <p className="trace-detail-id">
                                    <code>{trace.id}</code>
                                    <span>Started {timeLabel(trace.started_at)}</span>
                                </p>
                            </div>
                            <div className="trace-hero-metrics" aria-label="Trace summary">
                                <div><small>Duration</small><strong>{formatDuration(trace.duration_ms)}</strong></div>
                                <div><small>Spans</small><strong>{trace.span_count}</strong></div>
                                <div><small>Total tokens</small><strong>{tokenLabel(trace.usage.total_tokens)}</strong></div>
                                <div><small>Estimated cost</small><strong>{traceCost}</strong></div>
                            </div>
                        </header>

                        <section className="trace-workspace panel" aria-label="Trace explorer">
                            <div className="trace-explorer-toolbar">
                                <div className="trace-view-tabs" role="group" aria-label="Trace visualization">
                                    <button type="button" aria-pressed={mode === "timeline"} className={mode === "timeline" ? "active" : ""} onClick={() => setMode("timeline")}>
                                        <Activity size={15} aria-hidden="true" /> Timeline
                                    </button>
                                    <button type="button" aria-pressed={mode === "tree"} className={mode === "tree" ? "active" : ""} onClick={() => setMode("tree")}>
                                        <GitBranch size={15} aria-hidden="true" /> Tree
                                    </button>
                                </div>
                                <div className="trace-tree-controls" aria-label="Timeline controls">
                                    <button className="icon-button" type="button" aria-label="Collapse all span branches" onClick={collapseAll}>
                                        <Minus size={15} aria-hidden="true" />
                                    </button>
                                    <button className="icon-button" type="button" aria-label="Expand all span branches" onClick={expandAll}>
                                        <Plus size={15} aria-hidden="true" />
                                    </button>
                                    {mode === "timeline" ? (
                                        <>
                                            <span className="trace-control-divider" aria-hidden="true" />
                                            <button className="icon-button" type="button" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(1, value / 2))} disabled={zoom <= 1}>
                                                <Minus size={15} aria-hidden="true" />
                                            </button>
                                            <span className="trace-zoom-value">{zoom}×</span>
                                            <button className="icon-button" type="button" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(16, value * 2))} disabled={zoom >= 16}>
                                                <Plus size={15} aria-hidden="true" />
                                            </button>
                                            <button className="trace-fit-button" type="button" onClick={() => setZoom(1)}>Fit</button>
                                        </>
                                    ) : null}
                                </div>
                            </div>

                            <div className="trace-split-view trace-page-split">
                                <section className="trace-visualization" aria-label={mode === "timeline" ? "Span timeline" : "Span tree"}>
                                    {spans.length === 0 ? (
                                        <div className="trace-visual-empty">
                                            <Activity size={22} aria-hidden="true" />
                                            <strong>No spans recorded</strong>
                                            <span>This trace has no persisted span events.</span>
                                        </div>
                                    ) : mode === "timeline" ? (
                                        <div className="trace-timeline-scroll" role="region" aria-label="Timeline chart; scroll horizontally to inspect time range" tabIndex={0}>
                                            <div className="trace-timeline-content" style={{ minWidth: `${Math.max(720, 720 * zoom)}px` }}>
                                                <div className="trace-timeline-ruler" aria-hidden="true">
                                                    <span className="trace-ruler-label">Span</span>
                                                    <div className="trace-ruler-track">
                                                        {[0, 1, 2, 3, 4].map((tick) => (
                                                            <span className="trace-ruler-tick" key={tick} style={{ left: `${tick * 25}%` }}>
                                                                <i />{formatClock((timeline.duration * tick) / 4)}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                                <div className="trace-span-rows">
                                                    {rows.map(({ node, depth }) => {
                                                        const Icon = spanIcon(node.type);
                                                        const rawOffset = Date.parse(node.started_at) - Date.parse(trace.started_at);
                                                        const offset = Math.max(0, Math.min(timeline.duration, rawOffset));
                                                        const duration = node.duration_ms ?? Math.max(0, Date.now() - Date.parse(node.started_at));
                                                        const left = Math.min(100, (offset / timeline.duration) * 100);
                                                        const width = Math.max(0.7, Math.min(100 - left, (duration / timeline.duration) * 100));
                                                        const style = { "--span-depth": depth, "--span-left": `${left}%`, "--span-width": `${width}%` } as CSSProperties;
                                                        return (
                                                            <div className={`trace-row ${selected?.id === node.id ? "selected" : ""}`} key={node.id} style={style}>
                                                                <span className="trace-row-tree-action">
                                                                    {node.children.length ? (
                                                                        <button className="trace-branch-button" type="button" aria-label={`${collapsed.has(node.id) ? "Expand" : "Collapse"} ${node.name}`} aria-expanded={!collapsed.has(node.id)} onClick={() => toggleBranch(node.id)}>
                                                                            {collapsed.has(node.id) ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                                                                        </button>
                                                                    ) : <span className="trace-branch-spacer" />}
                                                                </span>
                                                                <button className="trace-row-select" type="button" aria-pressed={selected?.id === node.id} aria-label={`${node.name}, ${node.type}, ${node.status}, starts ${formatClock(offset)} after trace start, duration ${formatDuration(node.duration_ms)}`} title={`Starts ${formatClock(offset)} after trace start · ${formatDuration(node.duration_ms)}`} onClick={() => selectSpan(node)}>
                                                                    <span className="trace-row-label">
                                                                        <span className={`trace-span-kind ${spanClass(node.type)}`}><Icon size={14} aria-hidden="true" /></span>
                                                                        <span className="trace-row-copy">
                                                                            <strong>{node.name}</strong>
                                                                            <small>{node.type.replaceAll("_", " ")} · +{formatClock(offset)} · {formatDuration(node.duration_ms)}</small>
                                                                        </span>
                                                                        <span className={`trace-row-status ${statusTone(node.status)}`}>{node.status}</span>
                                                                    </span>
                                                                    <span className="trace-row-track" aria-hidden="true">
                                                                        <i className={`trace-timeline-bar ${spanClass(node.type)} ${statusTone(node.status)}`} />
                                                                    </span>
                                                                </button>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="trace-tree-scroll">
                                            {rows.map(({ node, depth }) => {
                                                const Icon = spanIcon(node.type);
                                                return (
                                                    <div className={`trace-tree-row ${selected?.id === node.id ? "selected" : ""}`} key={node.id} style={{ "--span-depth": depth } as CSSProperties}>
                                                        <span className="trace-row-tree-action">
                                                            {node.children.length ? (
                                                                <button className="trace-branch-button" type="button" aria-label={`${collapsed.has(node.id) ? "Expand" : "Collapse"} ${node.name}`} aria-expanded={!collapsed.has(node.id)} onClick={() => toggleBranch(node.id)}>
                                                                    {collapsed.has(node.id) ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                                                                </button>
                                                            ) : <span className="trace-branch-spacer" />}
                                                        </span>
                                                        <button className="trace-tree-select" type="button" aria-pressed={selected?.id === node.id} onClick={() => selectSpan(node)}>
                                                            <span className={`trace-span-kind ${spanClass(node.type)}`}><Icon size={14} aria-hidden="true" /></span>
                                                            <span className="trace-row-copy"><strong>{node.name}</strong><small>{node.type.replaceAll("_", " ")} · {formatDuration(node.duration_ms)}</small></span>
                                                            <StatusBadge status={node.status} />
                                                        </button>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                </section>

                                <aside className="trace-inspector-panel" aria-label="Span inspector">
                                    {selectedDetail ? (
                                        <>
                                            <div className="trace-inspector-title">
                                                <div className={`trace-inspector-mark ${spanClass(selectedDetail.type)}`}><SelectedIcon size={17} aria-hidden="true" /></div>
                                                <div className="trace-inspector-title-copy"><span className="panel-kicker">Span inspector</span><h2>{selectedDetail.name}</h2></div>
                                                <StatusBadge status={selectedDetail.status} />
                                            </div>
                                            <div className="trace-inspector-meta">
                                                <span><small>Type</small><b>{selectedDetail.type.replaceAll("_", " ")}</b></span>
                                                <span><small>Duration</small><b>{formatDuration(selectedDetail.duration_ms)}</b></span>
                                                <span><small>Started</small><b>{timeLabel(selectedDetail.started_at)}</b></span>
                                            </div>
                                            <section className="trace-inspector-usage" aria-label="Span token usage">
                                                <div><small>Input</small><strong>{tokenLabel(selectedDetail.usage.input_tokens)}</strong></div>
                                                <div><small>Output</small><strong>{tokenLabel(selectedDetail.usage.output_tokens)}</strong></div>
                                                <div><small>Total</small><strong>{tokenLabel(selectedDetail.usage.total_tokens)}</strong></div>
                                                {selectedDetail.estimated_cost ? <div><small>Run cost · est.</small><strong>{costLabel(selectedDetail.estimated_cost)}</strong></div> : null}
                                                {selectedDetail.usage.input_tokens_estimated ? <span className="trace-estimated-note">Input tokens estimated</span> : null}
                                            </section>
                                            {detailError ? <p className="trace-inline-error" role="alert">{detailError}</p> : null}
                                            {spanLoading ? <p className="trace-inspector-loading"><LoaderCircle className="spin" size={15} aria-hidden="true" /> Loading payload…</p> : null}
                                            {selectedDetail.attributes && Object.keys(selectedDetail.attributes).length ? <JsonBlock title="Attributes" value={selectedDetail.attributes} /> : null}
                                            {selectedDetail.input ? <JsonBlock title="Input" value={selectedDetail.input} /> : null}
                                            {selectedDetail.output ? <JsonBlock title="Output" value={selectedDetail.output} /> : null}
                                            {selectedDetail.error ? <JsonBlock title="Error" value={selectedDetail.error} /> : null}
                                            {Object.keys(selectedDetail.attributes).length === 0 && !selectedDetail.input && !selectedDetail.output && !selectedDetail.error ? <p className="trace-inspector-empty">No payload recorded for this span.</p> : null}
                                        </>
                                    ) : (
                                        <div className="trace-inspector-empty"><Search size={22} aria-hidden="true" /><strong>Select a span</strong><span>Choose a row to inspect its payload and usage.</span></div>
                                    )}
                                </aside>
                            </div>
                            <footer className="trace-workspace-footer">
                                <span><Clock3 size={14} aria-hidden="true" /> Started {timeLabel(trace.started_at)}</span>
                                <span>{trace.usage.input_tokens_estimated ? "Some input token counts are estimates" : "Token usage from model spans"}</span>
                                <span>Cost is estimated when available</span>
                            </footer>
                        </section>
                    </>
                ) : null}
            </div>
        </AppShell>
    );
}
