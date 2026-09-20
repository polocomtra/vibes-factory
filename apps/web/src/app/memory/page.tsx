"use client";

import {
    ArrowRight,
    BrainCircuit,
    CircleAlert,
    Database,
    LoaderCircle,
    Plus,
    X,
} from "lucide-react";
import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { AppShell } from "../../components/app-shell";
import { PaginationControls } from "../../components/pagination-controls";
import { apiFetch, readApiError } from "../../lib/api";
import {
    createMemoryStore,
    listMemoryStores,
    type MemoryStore,
} from "../../lib/memory";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };

function DialogActions({
    busy,
    onCancel,
}: {
    busy: boolean;
    onCancel: () => void;
}) {
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
                className="button primary-button"
                type="submit"
                disabled={busy}
            >
                {busy ? (
                    <LoaderCircle
                        className="spin"
                        size={15}
                        aria-hidden="true"
                    />
                ) : null}
                Create store
            </button>
        </div>
    );
}

function MemoryStoreCreateDialog({
    open,
    workspace,
    onClose,
    onCreated,
}: {
    open: boolean;
    workspace: Workspace | null;
    onClose: () => void;
    onCreated: (store: MemoryStore) => void;
}) {
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const dialogRef = useRef<HTMLElement>(null);

    useEffect(() => {
        if (!open) return;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        window.requestAnimationFrame(() =>
            dialogRef.current
                ?.querySelector<HTMLElement>("input, textarea, button")
                ?.focus(),
        );

        function focusableElements() {
            return Array.from(
                dialogRef.current?.querySelectorAll<HTMLElement>(
                    "button:not([disabled]), input:not([disabled]), textarea:not([disabled])",
                ) ?? [],
            );
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape" && !busy) {
                event.preventDefault();
                onClose();
                return;
            }
            if (event.key !== "Tab") return;
            const elements = focusableElements();
            if (!elements.length) return;
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
        };
    }, [busy, onClose, open]);

    if (!open) return null;

    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!workspace || !name.trim()) {
            setError("Enter a name for the memory store.");
            return;
        }
        setBusy(true);
        setError(null);
        try {
            const created = await createMemoryStore(workspace.id, {
                name: name.trim(),
                description: description.trim() || undefined,
            });
            onCreated(created);
            setName("");
            setDescription("");
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Unable to create memory store.",
            );
        } finally {
            setBusy(false);
        }
    }

    return (
        <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
                if (event.target === event.currentTarget && !busy) onClose();
            }}
        >
            <section
                className="modal-dialog memory-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="memory-store-dialog-title"
                aria-describedby="memory-store-dialog-description"
                ref={dialogRef}
                aria-busy={busy}
            >
                <div className="modal-heading">
                    <div>
                        <p className="panel-kicker">Workspace memory</p>
                        <h2 id="memory-store-dialog-title">
                            Create memory store
                        </h2>
                        <p
                            id="memory-store-dialog-description"
                            className="panel-copy"
                        >
                            Keep durable facts isolated in a workspace-scoped
                            store.
                        </p>
                    </div>
                    <button
                        className="icon-button modal-close"
                        type="button"
                        aria-label="Close dialog"
                        onClick={onClose}
                        disabled={busy}
                    >
                        <X size={16} aria-hidden="true" />
                    </button>
                </div>
                {error ? (
                    <div
                        className="form-error memory-dialog-error"
                        role="alert"
                    >
                        <CircleAlert size={15} aria-hidden="true" />
                        {error}
                    </div>
                ) : null}
                <form className="memory-dialog-form" onSubmit={submit}>
                    <label htmlFor="memory-store-overview-name">
                        Store name
                        <input
                            id="memory-store-overview-name"
                            value={name}
                            onChange={(event) => setName(event.target.value)}
                            placeholder="Product preferences"
                            autoComplete="off"
                            maxLength={255}
                            required
                        />
                    </label>
                    <label htmlFor="memory-store-overview-description">
                        Description <span>(optional)</span>
                        <textarea
                            id="memory-store-overview-description"
                            value={description}
                            onChange={(event) =>
                                setDescription(event.target.value)
                            }
                            placeholder="What should this store remember?"
                            rows={3}
                            maxLength={500}
                        />
                    </label>
                    <DialogActions busy={busy} onCancel={onClose} />
                </form>
            </section>
        </div>
    );
}

function MemoryStoreCard({ store }: { store: MemoryStore }) {
    return (
        <Link
            className="memory-store-card"
            href={`/memory/${store.id}`}
            aria-label={`Open memory store ${store.name}`}
        >
            <div className="memory-store-card-top">
                <span className="memory-store-icon" aria-hidden="true">
                    <Database size={20} />
                </span>
                <span className="memory-store-arrow" aria-hidden="true">
                    <ArrowRight size={17} />
                </span>
            </div>
            <h2>{store.name}</h2>
            <p>
                {store.description ||
                    "Durable reference data for agents in this workspace."}
            </p>
            <span className="memory-store-card-footer">
                Open store <ArrowRight size={14} aria-hidden="true" />
            </span>
        </Link>
    );
}

export default function MemoryPage() {
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [stores, setStores] = useState<MemoryStore[]>([]);
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(12);
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [cursorHistory, setCursorHistory] = useState<
        Array<string | undefined>
    >([undefined]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);

    useEffect(() => {
        let cancelled = false;

        async function load() {
            setLoading(true);
            setError(null);
            try {
                const response = await apiFetch("/v1/workspaces");
                if (!response.ok) throw new Error(await readApiError(response));
                const body = (await response.json()) as {
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
                const storePage = await listMemoryStores(
                    selectedWorkspace.id,
                    undefined,
                    12,
                );
                if (cancelled) return;
                setWorkspace(selectedWorkspace);
                setStores(storePage.data);
                setNextCursor(storePage.pagination.next_cursor);
                setCurrentPage(1);
                setCursorHistory([undefined]);
            } catch (reason: unknown) {
                if (!cancelled) {
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : "Unable to load memory stores.",
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
    }, []);

    async function loadPage(
        cursor: string | undefined,
        targetPage: number,
        size = pageSize,
    ) {
        if (!workspace) return;
        setLoading(true);
        setError(null);
        try {
            const page = await listMemoryStores(workspace.id, cursor, size);
            setStores(page.data);
            setNextCursor(page.pagination.next_cursor);
            setCurrentPage(targetPage);
            setCursorHistory((current) => {
                const next = current.slice(0, targetPage);
                next[targetPage - 1] = cursor;
                return next;
            });
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Unable to load memory stores.",
            );
        } finally {
            setLoading(false);
        }
    }

    async function changePage(targetPage: number) {
        if (!workspace || targetPage < 1 || targetPage === currentPage) {
            return;
        }
        const cursor =
            targetPage > currentPage
                ? (nextCursor ?? undefined)
                : cursorHistory[targetPage - 1];
        if (targetPage > currentPage && !nextCursor) return;
        await loadPage(cursor, targetPage);
    }

    async function changePageSize(size: number) {
        setPageSize(size);
        setCursorHistory([undefined]);
        await loadPage(undefined, 1, size);
    }

    return (
        <AppShell>
            <div className="pagination-page memory-page memory-overview-page">
                <div className="page-header memory-page-header">
                    <div>
                        <p className="eyebrow">VibesFactory / Connect</p>
                        <h1>Memory</h1>
                        <p className="page-description">
                            Durable facts that help agents remember users
                            without copying conversation history.
                        </p>
                    </div>
                    <div className="memory-header-actions">
                        <button
                            className="button primary-button"
                            type="button"
                            aria-haspopup="dialog"
                            aria-expanded={dialogOpen}
                            onClick={() => setDialogOpen(true)}
                        >
                            <Plus size={15} aria-hidden="true" />
                            New store
                        </button>
                    </div>
                </div>

                {error ? (
                    <div className="form-error memory-feedback" role="alert">
                        <CircleAlert size={15} aria-hidden="true" />
                        {error}
                    </div>
                ) : null}

                {loading ? (
                    <section className="memory-store-grid" role="status">
                        {Array.from({ length: 3 }, (_, index) => (
                            <div
                                className="memory-store-card memory-store-card-skeleton"
                                key={index}
                                aria-hidden="true"
                            >
                                <span />
                                <span />
                                <span />
                            </div>
                        ))}
                        <span className="sr-only">Loading memory stores…</span>
                    </section>
                ) : stores.length ? (
                    <section
                        className="memory-store-section"
                        aria-labelledby="memory-stores-title"
                    >
                        <div className="memory-store-grid">
                            {stores.map((store) => (
                                <MemoryStoreCard key={store.id} store={store} />
                            ))}
                        </div>
                    </section>
                ) : (
                    <section className="panel memory-empty" aria-live="polite">
                        <span className="memory-empty-icon" aria-hidden="true">
                            <BrainCircuit size={28} />
                        </span>
                        <p className="panel-kicker">Workspace memory</p>
                        <h2>Create a memory store</h2>
                        <p className="panel-copy">
                            Stores keep durable facts isolated per workspace.
                        </p>
                        <button
                            className="button primary-button"
                            type="button"
                            onClick={() => setDialogOpen(true)}
                        >
                            <Plus size={15} aria-hidden="true" />
                            Create memory store
                        </button>
                    </section>
                )}

                {stores.length ? (
                    <PaginationControls
                        page={currentPage}
                        pageSize={pageSize}
                        hasPreviousPage={currentPage > 1}
                        hasNextPage={Boolean(nextCursor)}
                        disabled={loading}
                        resetPageOnSizeChange={false}
                        onPageChange={(page) => void changePage(page)}
                        onPageSizeChange={(size) => void changePageSize(size)}
                        ariaLabel="Memory stores pagination"
                    />
                ) : null}
            </div>
            <MemoryStoreCreateDialog
                open={dialogOpen}
                workspace={workspace}
                onClose={() => setDialogOpen(false)}
                onCreated={(created) => {
                    setStores((current) => [created, ...current]);
                    setDialogOpen(false);
                }}
            />
        </AppShell>
    );
}
