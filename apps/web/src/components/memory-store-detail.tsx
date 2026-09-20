"use client";

import {
    ArrowLeft,
    BrainCircuit,
    CheckCircle2,
    CircleAlert,
    Clock3,
    Edit3,
    LoaderCircle,
    Plus,
    Search,
    Trash2,
    X,
} from "lucide-react";
import Link from "next/link";
import {
    type FormEvent,
    useCallback,
    useEffect,
    useRef,
    useState,
} from "react";

import { AppShell } from "./app-shell";
import { PaginationControls } from "./pagination-controls";
import { fetchAgents, type Agent } from "../lib/agents";
import { apiFetch, readApiError } from "../lib/api";
import {
    createMemoryItem,
    createMemoryStore,
    deleteMemoryItem,
    listMemoryItems,
    listMemoryStores,
    searchMemory,
    updateMemoryItem,
    type MemoryItem,
    type MemoryStore,
    type MemoryType,
} from "../lib/memory";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };
type DialogMode = "store" | "create" | "edit" | "delete" | null;
type Scope = "user" | "agent";

const memoryTypes: MemoryType[] = [
    "PROFILE",
    "SEMANTIC",
    "SUMMARY",
    "PROCEDURAL",
];

function dateLabel(value: string) {
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(value));
}

function scopeLabel(item: MemoryItem, agents: Agent[]) {
    if (item.user_id) return "My memory";
    if (!item.agent_id) return "Agent global";
    return `Agent global · ${agents.find((agent) => agent.id === item.agent_id)?.name ?? "Agent"}`;
}

function MemoryTypeBadge({ type }: { type: MemoryType }) {
    return (
        <span className="status-badge info">
            <span aria-hidden="true" />
            {type}
        </span>
    );
}

function EmptyMemoryState({
    hasStore,
    onCreateStore,
    onCreateMemory,
}: {
    hasStore: boolean;
    onCreateStore: () => void;
    onCreateMemory: () => void;
}) {
    return (
        <section className="panel memory-empty" aria-live="polite">
            <span className="memory-empty-icon" aria-hidden="true">
                <BrainCircuit size={28} />
            </span>
            <p className="panel-kicker">
                {hasStore ? "Memory browser" : "Workspace memory"}
            </p>
            <h2>
                {hasStore
                    ? "No memories match these filters"
                    : "Create a memory store"}
            </h2>
            <p className="panel-copy">
                {hasStore
                    ? "Add a durable fact manually or let a successful agent run extract one."
                    : "Stores keep embeddings and durable facts isolated per workspace."}
            </p>
            <button
                className="button primary-button"
                type="button"
                onClick={hasStore ? onCreateMemory : onCreateStore}
            >
                <Plus size={15} aria-hidden="true" />
                {hasStore ? "Add memory" : "Create memory store"}
            </button>
        </section>
    );
}

export function MemoryStoreDetailView({
    memoryStoreId,
}: {
    memoryStoreId: string;
}) {
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [stores, setStores] = useState<MemoryStore[]>([]);
    const [store, setStore] = useState<MemoryStore | null>(null);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [items, setItems] = useState<MemoryItem[]>([]);
    const [type, setType] = useState<MemoryType | "">("");
    const [agentId, setAgentId] = useState("");
    const [query, setQuery] = useState("");
    const [searching, setSearching] = useState(false);
    const [searchMode, setSearchMode] = useState(false);
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(12);
    const [cursorHistory, setCursorHistory] = useState<Array<string | undefined>>([
        undefined,
    ]);
    const [itemsLoading, setItemsLoading] = useState(false);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [dialog, setDialog] = useState<DialogMode>(null);
    const [selected, setSelected] = useState<MemoryItem | null>(null);
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [content, setContent] = useState("");
    const [itemType, setItemType] = useState<MemoryType>("PROFILE");
    const [scope, setScope] = useState<Scope>("user");
    const [scopeAgentId, setScopeAgentId] = useState("");
    const [importance, setImportance] = useState("0.7");
    const [confidence, setConfidence] = useState("0.9");
    const [error, setError] = useState<string | null>(null);
    const [dialogError, setDialogError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const dialogRef = useRef<HTMLElement>(null);
    const createStoreTriggerRef = useRef<HTMLButtonElement>(null);

    const loadItems = useCallback(
        async (
            nextStore: MemoryStore,
            cursor?: string,
            targetPage = 1,
            size = 12,
        ) => {
            setItemsLoading(true);
            try {
                const page = await listMemoryItems(nextStore.id, {
                    type: type || undefined,
                    agentId: agentId || undefined,
                    cursor,
                    limit: size,
                });
                setItems(page.data);
                setNextCursor(page.pagination.next_cursor);
                setCurrentPage(targetPage);
                setCursorHistory((current) => {
                    const next = current.slice(0, targetPage);
                    next[targetPage - 1] = cursor;
                    return next;
                });
                setSearchMode(false);
            } finally {
                setItemsLoading(false);
            }
        },
        [agentId, type],
    );

    useEffect(() => {
        let cancelled = false;

        async function load() {
            setLoading(true);
            setError(null);
            try {
                const workspaceResponse = await apiFetch("/v1/workspaces");
                if (!workspaceResponse.ok) {
                    throw new Error(await readApiError(workspaceResponse));
                }
                const body = (await workspaceResponse.json()) as {
                    data: Workspace[];
                };
                const savedId = window.localStorage.getItem("vf-workspace-id");
                const selectedWorkspace =
                    body.data.find((item) => item.id === savedId) ??
                    body.data[0] ??
                    null;
                if (!selectedWorkspace) {
                    throw new Error(
                        "No workspace is available for this account.",
                    );
                }

                const [storePage, agentList] = await Promise.all([
                    listMemoryStores(selectedWorkspace.id, undefined, 100),
                    fetchAgents(selectedWorkspace.id, "", "ACTIVE"),
                ]);
                if (cancelled) return;
                setWorkspace(selectedWorkspace);
                setStores(storePage.data);
                const selectedStore = storePage.data.find(
                    (item) => item.id === memoryStoreId,
                );
                if (!selectedStore) {
                    throw new Error("Memory store not found.");
                }
                setStore(selectedStore);
                setAgents(agentList);
            } catch (reason: unknown) {
                if (!cancelled) {
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : "Unable to load memory.",
                    );
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        void load();
        return () => {
            cancelled = true;
        };
    }, [memoryStoreId]);

    async function changePage(targetPage: number) {
        if (!store || targetPage < 1 || targetPage === currentPage) return;
        const cursor =
            targetPage > currentPage
                ? nextCursor ?? undefined
                : cursorHistory[targetPage - 1];
        if (targetPage > currentPage && !nextCursor) return;
        setError(null);
        try {
            await loadItems(store, cursor, targetPage, pageSize);
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Unable to load memories.",
            );
            setItemsLoading(false);
        }
    }

    async function changePageSize(size: number) {
        if (!store) return;
        setPageSize(size);
        setCursorHistory([undefined]);
        setCurrentPage(1);
    }

    useEffect(() => {
        if (!store || loading) return;
        setError(null);
        void loadItems(store, undefined, 1, pageSize).catch((reason: unknown) => {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Unable to load memories.",
            );
        });
    }, [loadItems, loading, pageSize, store]);

    useEffect(() => {
        if (!dialog) return;

        const previousOverflow = document.body.style.overflow;
        const trigger = createStoreTriggerRef.current;
        document.body.style.overflow = "hidden";
        window.requestAnimationFrame(() =>
            dialogRef.current
                ?.querySelector<HTMLElement>(
                    "input, textarea, select, button:not([disabled])",
                )
                ?.focus(),
        );

        function focusableElements() {
            return Array.from(
                dialogRef.current?.querySelectorAll<HTMLElement>(
                    "button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled])",
                ) ?? [],
            );
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape" && !busy) {
                event.preventDefault();
                setDialog(null);
                return;
            }
            if (event.key !== "Tab") return;
            const elements = focusableElements();
            if (elements.length === 0) return;
            const first = elements[0];
            const last = elements[elements.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }

        window.addEventListener("keydown", handleKeyDown);
        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener("keydown", handleKeyDown);
            window.requestAnimationFrame(() => trigger?.focus());
        };
    }, [busy, dialog]);

    function clearFeedback() {
        setError(null);
        setDialogError(null);
        setMessage(null);
    }

    function openStoreDialog() {
        clearFeedback();
        setName("");
        setDescription("");
        setDialog("store");
    }

    function openCreateDialog() {
        clearFeedback();
        setContent("");
        setItemType("PROFILE");
        setScope("user");
        setScopeAgentId("");
        setImportance("0.7");
        setConfidence("0.9");
        setDialog("create");
    }

    function openEditDialog(item: MemoryItem) {
        clearFeedback();
        setSelected(item);
        setContent(item.content);
        setItemType(item.type);
        setImportance(String(item.importance ?? 0.7));
        setConfidence(String(item.confidence ?? 0.9));
        setDialog("edit");
    }

    function openDeleteDialog(item: MemoryItem) {
        clearFeedback();
        setSelected(item);
        setDialog("delete");
    }

    async function runSearch() {
        if (!store || !query.trim()) return;
        setSearching(true);
        clearFeedback();
        try {
            const response = await searchMemory(store.id, {
                query: query.trim(),
                agent_id: agentId || undefined,
                top_k: 5,
            });
            setItems(response.data);
            setNextCursor(null);
            setCurrentPage(1);
            setCursorHistory([undefined]);
            setSearchMode(true);
            setMessage(
                `Semantic search completed in ${response.latency_ms} ms.`,
            );
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Memory search failed.",
            );
        } finally {
            setSearching(false);
        }
    }

    async function submitDialog() {
        setBusy(true);
        setDialogError(null);
        setError(null);
        setMessage(null);
        try {
            if (dialog === "store") {
                if (!workspace || !name.trim()) {
                    throw new Error("Enter a name for the memory store.");
                }
                const created = await createMemoryStore(workspace.id, {
                    name: name.trim(),
                    description: description.trim() || undefined,
                });
                setStores((current) => [created, ...current]);
                setStore(created);
                setDialog(null);
                setMessage("Memory store created.");
            } else if (dialog === "create") {
                if (!store || !content.trim()) {
                    throw new Error("Enter the memory content.");
                }
                if (scope === "agent" && !scopeAgentId) {
                    throw new Error("Select an agent for agent-global memory.");
                }
                const created = await createMemoryItem(store.id, {
                    agent_id: scope === "agent" ? scopeAgentId : null,
                    type: itemType,
                    content: content.trim(),
                    importance: Number(importance),
                    confidence: Number(confidence),
                });
                setItems((current) => [created, ...current]);
                setDialog(null);
                setMessage("Memory added.");
            } else if (dialog === "edit" && selected) {
                if (!content.trim())
                    throw new Error("Enter the memory content.");
                const updated = await updateMemoryItem(selected.id, {
                    content: content.trim(),
                    type: itemType,
                    importance: Number(importance),
                    confidence: Number(confidence),
                });
                setItems((current) =>
                    current.map((item) =>
                        item.id === updated.id ? updated : item,
                    ),
                );
                setDialog(null);
                setMessage("Memory corrected.");
            } else if (dialog === "delete" && selected) {
                await deleteMemoryItem(selected.id);
                setItems((current) =>
                    current.filter((item) => item.id !== selected.id),
                );
                setSelected(null);
                setDialog(null);
                setMessage("Memory deleted.");
            }
        } catch (reason: unknown) {
            setDialogError(
                reason instanceof Error
                    ? reason.message
                    : "Memory operation failed.",
            );
        } finally {
            setBusy(false);
        }
    }

    const dialogTitle =
        dialog === "store"
            ? "Create memory store"
            : dialog === "create"
              ? "Add memory"
              : dialog === "edit"
                ? "Correct memory"
                : "Delete memory";

    return (
        <AppShell>
            <div className="pagination-page memory-page">
                <Link className="memory-back-link" href="/memory">
                    <ArrowLeft size={15} aria-hidden="true" />
                    Memory stores
                </Link>
                <div className="page-header memory-page-header">
                    <div>
                        <p className="eyebrow">VibesFactory / Connect</p>
                        <h1>{store?.name ?? "Memory store"}</h1>
                        <p className="page-description">
                            {store?.description ||
                                "Durable facts available to this workspace and its agents."}
                        </p>
                    </div>
                    <div className="memory-header-actions">
                        <button
                            ref={createStoreTriggerRef}
                            className="button secondary-button"
                            type="button"
                            aria-haspopup="dialog"
                            aria-expanded={dialog === "store"}
                            onClick={openStoreDialog}
                        >
                            <Plus size={15} aria-hidden="true" />
                            New store
                        </button>
                        <button
                            className="button primary-button"
                            type="button"
                            aria-haspopup="dialog"
                            aria-expanded={dialog === "create"}
                            onClick={openCreateDialog}
                            disabled={!store || loading}
                        >
                            <Plus size={15} aria-hidden="true" />
                            Add memory
                        </button>
                    </div>
                </div>

                {error ? (
                    <div className="form-error memory-feedback" role="alert">
                        <CircleAlert size={15} aria-hidden="true" />
                        {error}
                    </div>
                ) : null}
                {message ? (
                    <div className="form-success memory-feedback" role="status">
                        <CheckCircle2 size={15} aria-hidden="true" />
                        {message}
                    </div>
                ) : null}

                <section
                    className="panel memory-toolbar memory-detail-toolbar"
                    aria-label="Memory filters"
                >
                    <label className="memory-filter-field">
                        <span>Type</span>
                        <select
                            value={type}
                            onChange={(event) => {
                                setSearchMode(false);
                                setType(event.target.value as MemoryType | "");
                            }}
                        >
                            <option value="">All types</option>
                            {memoryTypes.map((item) => (
                                <option key={item} value={item}>
                                    {item}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className="memory-filter-field">
                        <span>Agent scope</span>
                        <select
                            value={agentId}
                            onChange={(event) => {
                                setSearchMode(false);
                                setAgentId(event.target.value);
                            }}
                        >
                            <option value="">All agents</option>
                            {agents.map((item) => (
                                <option key={item.id} value={item.id}>
                                    {item.name}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className="memory-search-field">
                        <span>Semantic search</span>
                        <span className="memory-search-input">
                            <Search size={15} aria-hidden="true" />
                            <input
                                value={query}
                                onChange={(event) =>
                                    setQuery(event.target.value)
                                }
                                onKeyDown={(event) => {
                                    if (event.key === "Enter") void runSearch();
                                }}
                                placeholder="Search durable memory…"
                            />
                            <button
                                className="icon-button"
                                type="button"
                                aria-label="Search memories"
                                onClick={() => void runSearch()}
                                disabled={searching || !query.trim() || !store}
                            >
                                {searching ? (
                                    <LoaderCircle
                                        className="spin"
                                        size={15}
                                        aria-hidden="true"
                                    />
                                ) : (
                                    <Search size={15} aria-hidden="true" />
                                )}
                            </button>
                        </span>
                    </label>
                </section>

                {loading ? (
                    <section className="panel memory-state" role="status">
                        <div className="memory-skeleton-heading" />
                        <div className="memory-skeleton-row" />
                        <div className="memory-skeleton-row short" />
                        <span className="sr-only">Loading memory…</span>
                    </section>
                ) : !stores.length ? (
                    <EmptyMemoryState
                        hasStore={false}
                        onCreateStore={openStoreDialog}
                        onCreateMemory={openCreateDialog}
                    />
                ) : (
                    <>
                        {items.length === 0 ? (
                            <EmptyMemoryState
                                hasStore
                                onCreateStore={openStoreDialog}
                                onCreateMemory={openCreateDialog}
                            />
                        ) : (
                            <section
                                className="panel memory-list"
                                aria-label="Memory browser"
                            >
                                <div className="memory-list-heading">
                                    <h2>
                                        {searchMode
                                            ? "Semantic matches"
                                            : "Stored memories"}
                                    </h2>
                                </div>
                                <div className="memory-list-rows">
                                    {items.map((item) => (
                                        <article
                                            className="memory-row"
                                            key={item.id}
                                        >
                                            <div className="memory-row-main">
                                                <div className="memory-row-topline">
                                                    <MemoryTypeBadge
                                                        type={item.type}
                                                    />
                                                    <span className="memory-scope">
                                                        {scopeLabel(
                                                            item,
                                                            agents,
                                                        )}
                                                    </span>
                                                </div>
                                                <p>{item.content}</p>
                                                <div className="memory-row-meta">
                                                    <span>
                                                        Confidence{" "}
                                                        {item.confidence ===
                                                        null
                                                            ? "—"
                                                            : `${Math.round(item.confidence * 100)}%`}
                                                    </span>
                                                    <span>
                                                        <Clock3
                                                            size={13}
                                                            aria-hidden="true"
                                                        />
                                                        {dateLabel(
                                                            item.updated_at,
                                                        )}
                                                    </span>
                                                    {item.expires_at ? (
                                                        <span>
                                                            Expires{" "}
                                                            {dateLabel(
                                                                item.expires_at,
                                                            )}
                                                        </span>
                                                    ) : null}
                                                    {item.source_run_id ? (
                                                        <code>
                                                            run{" "}
                                                            {item.source_run_id.slice(
                                                                0,
                                                                8,
                                                            )}
                                                            …
                                                        </code>
                                                    ) : (
                                                        <span>Manual</span>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="memory-row-actions">
                                                <button
                                                    className="icon-button"
                                                    type="button"
                                                    aria-label={`Edit memory: ${item.content.slice(0, 40)}`}
                                                    onClick={() =>
                                                        openEditDialog(item)
                                                    }
                                                >
                                                    <Edit3
                                                        size={15}
                                                        aria-hidden="true"
                                                    />
                                                </button>
                                                <button
                                                    className="icon-button danger-icon-button"
                                                    type="button"
                                                    aria-label={`Delete memory: ${item.content.slice(0, 40)}`}
                                                    onClick={() =>
                                                        openDeleteDialog(item)
                                                    }
                                                >
                                                    <Trash2
                                                        size={15}
                                                        aria-hidden="true"
                                                    />
                                                </button>
                                            </div>
                                        </article>
                                    ))}
                                </div>
                            </section>
                        )}
                        {!searchMode && items.length ? (
                            <PaginationControls
                                page={currentPage}
                                pageSize={pageSize}
                                hasPreviousPage={currentPage > 1}
                                hasNextPage={Boolean(nextCursor)}
                                disabled={itemsLoading}
                                resetPageOnSizeChange={false}
                                onPageChange={(page) => void changePage(page)}
                                onPageSizeChange={(size) =>
                                    void changePageSize(size)
                                }
                                ariaLabel="Memory items pagination"
                            />
                        ) : null}
                    </>
                )}

                {dialog ? (
                    <div
                        className="modal-backdrop"
                        role="presentation"
                        onMouseDown={(event) => {
                            if (event.target === event.currentTarget && !busy)
                                setDialog(null);
                        }}
                    >
                        <section
                            className="modal-dialog memory-dialog"
                            role="dialog"
                            aria-modal="true"
                            aria-labelledby="memory-dialog-title"
                            aria-describedby="memory-dialog-description"
                            ref={dialogRef}
                            aria-busy={busy}
                        >
                            <div className="modal-heading">
                                <div>
                                    <p className="panel-kicker">
                                        Memory browser
                                    </p>
                                    <h2 id="memory-dialog-title">
                                        {dialogTitle}
                                    </h2>
                                    <p
                                        id="memory-dialog-description"
                                        className="panel-copy"
                                    >
                                        {dialog === "delete"
                                            ? "Confirm deletion to exclude this memory from future retrieval."
                                            : "Memory content is reference data and is never treated as an instruction."}
                                    </p>
                                </div>
                                <button
                                    className="icon-button modal-close"
                                    type="button"
                                    aria-label="Close dialog"
                                    onClick={() => setDialog(null)}
                                    disabled={busy}
                                >
                                    <X size={16} aria-hidden="true" />
                                </button>
                            </div>

                            {dialogError ? (
                                <div
                                    className="form-error memory-dialog-error"
                                    role="alert"
                                >
                                    <CircleAlert size={15} aria-hidden="true" />
                                    {dialogError}
                                </div>
                            ) : null}

                            {dialog === "store" ? (
                                <form
                                    className="memory-dialog-form"
                                    onSubmit={(event) => {
                                        event.preventDefault();
                                        void submitDialog();
                                    }}
                                >
                                    <label htmlFor="memory-store-name">
                                        Store name
                                        <input
                                            id="memory-store-name"
                                            value={name}
                                            onChange={(event) =>
                                                setName(event.target.value)
                                            }
                                            placeholder="Product preferences"
                                            autoComplete="off"
                                            maxLength={255}
                                            required
                                        />
                                    </label>
                                    <label htmlFor="memory-store-description">
                                        Description <span>(optional)</span>
                                        <textarea
                                            id="memory-store-description"
                                            value={description}
                                            onChange={(event) =>
                                                setDescription(
                                                    event.target.value,
                                                )
                                            }
                                            placeholder="What should this store remember?"
                                            rows={3}
                                            maxLength={500}
                                        />
                                    </label>
                                    <p className="field-helper">
                                        This workspace uses multilingual
                                        E5-small embeddings at 384 dimensions.
                                    </p>
                                    <DialogActions
                                        busy={busy}
                                        mode="store"
                                        onCancel={() => setDialog(null)}
                                    />
                                </form>
                            ) : dialog === "delete" ? (
                                <div className="memory-dialog-form">
                                    <p className="memory-delete-copy">
                                        This removes “
                                        {selected?.content.slice(0, 110)}” from
                                        future retrieval. The source
                                        conversation remains unchanged.
                                    </p>
                                    <DialogActions
                                        busy={busy}
                                        mode="delete"
                                        onCancel={() => setDialog(null)}
                                        onSubmit={() => void submitDialog()}
                                    />
                                </div>
                            ) : (
                                <form
                                    className="memory-dialog-form"
                                    onSubmit={(event) => {
                                        event.preventDefault();
                                        void submitDialog();
                                    }}
                                >
                                    <label htmlFor="memory-type">
                                        Memory type
                                        <select
                                            id="memory-type"
                                            value={itemType}
                                            onChange={(event) =>
                                                setItemType(
                                                    event.target
                                                        .value as MemoryType,
                                                )
                                            }
                                        >
                                            {memoryTypes.map((item) => (
                                                <option key={item} value={item}>
                                                    {item}
                                                </option>
                                            ))}
                                        </select>
                                    </label>
                                    {dialog === "create" ? (
                                        <>
                                            <label htmlFor="memory-scope">
                                                Scope
                                                <select
                                                    id="memory-scope"
                                                    value={scope}
                                                    onChange={(event) =>
                                                        setScope(
                                                            event.target
                                                                .value as Scope,
                                                        )
                                                    }
                                                >
                                                    <option value="user">
                                                        My memory
                                                    </option>
                                                    <option value="agent">
                                                        Agent-global
                                                    </option>
                                                </select>
                                            </label>
                                            {scope === "agent" ? (
                                                <label htmlFor="memory-agent">
                                                    Agent
                                                    <select
                                                        id="memory-agent"
                                                        value={scopeAgentId}
                                                        onChange={(event) =>
                                                            setScopeAgentId(
                                                                event.target
                                                                    .value,
                                                            )
                                                        }
                                                        required
                                                    >
                                                        <option value="">
                                                            Select an agent
                                                        </option>
                                                        {agents.map((item) => (
                                                            <option
                                                                key={item.id}
                                                                value={item.id}
                                                            >
                                                                {item.name}
                                                            </option>
                                                        ))}
                                                    </select>
                                                </label>
                                            ) : null}
                                        </>
                                    ) : null}
                                    <label htmlFor="memory-content">
                                        Content
                                        <textarea
                                            id="memory-content"
                                            value={content}
                                            onChange={(event) =>
                                                setContent(event.target.value)
                                            }
                                            placeholder="Example: Prefers concise answers with bullet points."
                                            rows={5}
                                            maxLength={10_000}
                                            required
                                        />
                                    </label>
                                    <div className="field-grid memory-score-grid">
                                        <label htmlFor="memory-importance">
                                            Importance
                                            <input
                                                id="memory-importance"
                                                type="number"
                                                min="0"
                                                max="1"
                                                step="0.1"
                                                value={importance}
                                                onChange={(event) =>
                                                    setImportance(
                                                        event.target.value,
                                                    )
                                                }
                                            />
                                        </label>
                                        <label htmlFor="memory-confidence">
                                            Confidence
                                            <input
                                                id="memory-confidence"
                                                type="number"
                                                min="0"
                                                max="1"
                                                step="0.1"
                                                value={confidence}
                                                onChange={(event) =>
                                                    setConfidence(
                                                        event.target.value,
                                                    )
                                                }
                                            />
                                        </label>
                                    </div>
                                    <p className="field-helper">
                                        Keep durable facts concise. Secrets,
                                        credentials, and transient requests are
                                        not stored.
                                    </p>
                                    <DialogActions
                                        busy={busy}
                                        mode={dialog}
                                        onCancel={() => setDialog(null)}
                                    />
                                </form>
                            )}
                        </section>
                    </div>
                ) : null}
            </div>
        </AppShell>
    );
}

function DialogActions({
    busy,
    mode,
    onCancel,
    onSubmit,
}: {
    busy: boolean;
    mode: Exclude<DialogMode, null>;
    onCancel: () => void;
    onSubmit?: () => void;
}) {
    const isDelete = mode === "delete";
    return (
        <div className="modal-actions">
            <button
                className="button secondary-button"
                type="button"
                onClick={onCancel}
                disabled={busy}
            >
                Cancel
            </button>
            <button
                className={
                    isDelete ? "button danger-button" : "button primary-button"
                }
                type={onSubmit ? "button" : "submit"}
                onClick={onSubmit}
                disabled={busy}
            >
                {busy ? (
                    <LoaderCircle
                        className="spin"
                        size={15}
                        aria-hidden="true"
                    />
                ) : null}
                {isDelete
                    ? "Delete memory"
                    : mode === "edit"
                      ? "Save correction"
                      : mode === "store"
                        ? "Create store"
                        : "Add memory"}
            </button>
        </div>
    );
}
