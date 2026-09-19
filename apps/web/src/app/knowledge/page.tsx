"use client";

import {
    Archive,
    Boxes,
    CheckCircle2,
    FileText,
    LoaderCircle,
    Plus,
    UploadCloud,
    X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "../../components/app-shell";
import { apiFetch, readApiError } from "../../lib/api";
import {
    archiveKnowledgeBase,
    createKnowledgeBase,
    listKnowledgeBases,
    type KnowledgeBase,
} from "../../lib/knowledge";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };
type WorkspaceResponse = { data?: Workspace[] };

function KnowledgeStatus({ status }: { status: KnowledgeBase["status"] }) {
    return (
        <span
            className={`status-badge ${status === "ACTIVE" ? "success" : "muted"}`}
        >
            <span aria-hidden="true" />
            {status === "ACTIVE" ? "Active" : "Archived"}
        </span>
    );
}

export default function KnowledgePage() {
    const router = useRouter();
    const createTriggerRef = useRef<HTMLButtonElement>(null);
    const closeButtonRef = useRef<HTMLButtonElement>(null);
    const dialogRef = useRef<HTMLElement>(null);
    const creatingRef = useRef(false);
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [items, setItems] = useState<KnowledgeBase[]>([]);
    const [loading, setLoading] = useState(true);
    const [workspaceLoading, setWorkspaceLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const [creating, setCreating] = useState(false);
    const [createOpen, setCreateOpen] = useState(false);
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");

    useEffect(() => {
        let cancelled = false;

        async function load() {
            try {
                const response = await apiFetch("/v1/workspaces");
                if (!response.ok) throw new Error(await readApiError(response));

                const body = (await response.json()) as WorkspaceResponse;
                const workspaces = body.data ?? [];
                const savedId = window.localStorage.getItem("vf-workspace-id");
                const selected =
                    workspaces.find((item) => item.id === savedId) ??
                    workspaces[0] ??
                    null;

                if (cancelled) return;
                setWorkspace(selected);
                if (!selected) {
                    setError("No workspace is available for this account.");
                    return;
                }

                const page = await listKnowledgeBases(
                    selected.id,
                    undefined,
                    "ACTIVE",
                );
                if (!cancelled) setItems(page.data);
            } catch (reason: unknown) {
                if (!cancelled) {
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : "Unable to load knowledge bases.",
                    );
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                    setWorkspaceLoading(false);
                }
            }
        }

        void load();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        if (!createOpen) return;

        const previousOverflow = document.body.style.overflow;
        const trigger = createTriggerRef.current;
        document.body.style.overflow = "hidden";
        window.requestAnimationFrame(() => closeButtonRef.current?.focus());

        function focusableElements() {
            return Array.from(
                dialogRef.current?.querySelectorAll<HTMLElement>(
                    "button:not([disabled]), input:not([disabled]), textarea:not([disabled])",
                ) ?? [],
            );
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape" && !creatingRef.current) {
                event.preventDefault();
                setCreateOpen(false);
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
    }, [createOpen]);

    async function create() {
        setMessage(null);
        setError(null);

        if (!workspace) {
            setError("Select a workspace before creating a knowledge base.");
            return;
        }

        const trimmedName = name.trim();
        if (!trimmedName) {
            setError("Enter a name for the knowledge base.");
            return;
        }

        creatingRef.current = true;
        setCreating(true);
        try {
            const kb = await createKnowledgeBase(workspace.id, {
                name: trimmedName,
                description: description.trim() || undefined,
            });
            setItems((current) => [kb, ...current]);
            setName("");
            setDescription("");
            setCreateOpen(false);
            setMessage(`“${kb.name}” was created. You can add sources now.`);
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Unable to create knowledge base.",
            );
        } finally {
            creatingRef.current = false;
            setCreating(false);
        }
    }

    async function archive(id: string) {
        setError(null);
        try {
            await archiveKnowledgeBase(id);
            setItems((current) => current.filter((item) => item.id !== id));
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Unable to archive knowledge base.",
            );
        }
    }

    return (
        <AppShell>
            <div className="pagination-page knowledge-page">
                <div className="page-header knowledge-page-header">
                    <div>
                        <p className="eyebrow">VibesFactory / Connect</p>
                        <h1>Knowledge</h1>
                        <p className="page-description">
                            Durable sources that keep agent answers grounded and
                            inspectable.
                        </p>
                    </div>
                    <div className="knowledge-header-actions">
                        <button
                            ref={createTriggerRef}
                            className="button primary-button"
                            type="button"
                            aria-haspopup="dialog"
                            aria-controls="knowledge-create-dialog"
                            aria-expanded={createOpen}
                            disabled={workspaceLoading}
                            onClick={() => {
                                setError(null);
                                setMessage(null);
                                setCreateOpen(true);
                            }}
                        >
                            <Plus size={16} aria-hidden="true" />
                            Create knowledge
                        </button>
                    </div>
                </div>

                {error && !createOpen ? (
                    <div className="form-error knowledge-feedback" role="alert">
                        {error}
                    </div>
                ) : null}
                {message ? (
                    <p
                        className="form-success knowledge-feedback"
                        role="status"
                    >
                        {message}
                    </p>
                ) : null}

                {loading ? (
                    <section
                        className="panel agent-state knowledge-empty"
                        role="status"
                    >
                        <LoaderCircle
                            className="spin"
                            size={18}
                            aria-hidden="true"
                        />
                        Loading knowledge bases…
                    </section>
                ) : items.length === 0 ? (
                    <section className="panel agent-empty-state knowledge-empty">
                        <UploadCloud size={30} aria-hidden="true" />
                        <h2>No active knowledge bases yet</h2>
                        <p className="panel-copy">
                            Create a knowledge base, then upload your first
                            source.
                        </p>
                    </section>
                ) : (
                    <section
                        className="tools-card-grid knowledge-card-grid"
                        aria-label="Knowledge bases"
                    >
                        {items.map((item) => (
                            <article className="tool-agent-card" key={item.id}>
                                <button
                                    className="tool-agent-card-main"
                                    type="button"
                                    onClick={() =>
                                        router.push(`/knowledge/${item.id}`)
                                    }
                                >
                                    <div className="tool-agent-card-top">
                                        <span className="tool-agent-icon">
                                            <Boxes
                                                size={19}
                                                aria-hidden="true"
                                            />
                                        </span>
                                        <KnowledgeStatus status={item.status} />
                                    </div>
                                    <div className="tool-agent-card-title">
                                        <h2>{item.name}</h2>
                                    </div>
                                    <p>
                                        {item.description ||
                                            "No description yet."}
                                    </p>
                                    <div className="tool-agent-card-meta">
                                        <span>
                                            <small>Documents</small>
                                            <b>
                                                {item.ready_document_count}/
                                                {item.document_count} ready
                                            </b>
                                        </span>
                                        <span>
                                            <small>Embedding</small>
                                            <code>e5-small</code>
                                        </span>
                                        <span>
                                            <small>Revision</small>
                                            <code>
                                                {item.embedding_revision.slice(
                                                    0,
                                                    8,
                                                )}
                                                …
                                            </code>
                                        </span>
                                    </div>
                                </button>
                                <footer>
                                    <span>
                                        <FileText
                                            size={14}
                                            aria-hidden="true"
                                        />
                                        {item.document_count} source
                                        {item.document_count === 1 ? "" : "s"}
                                    </span>
                                    {item.status === "ACTIVE" ? (
                                        <button
                                            className="text-button"
                                            type="button"
                                            onClick={() =>
                                                void archive(item.id)
                                            }
                                        >
                                            <Archive
                                                size={14}
                                                aria-hidden="true"
                                            />
                                            Archive
                                        </button>
                                    ) : null}
                                </footer>
                            </article>
                        ))}
                    </section>
                )}

                {createOpen ? (
                    <div
                        className="modal-backdrop knowledge-modal-backdrop"
                        role="presentation"
                        onMouseDown={(event) => {
                            if (
                                event.target === event.currentTarget &&
                                !creating
                            ) {
                                setCreateOpen(false);
                            }
                        }}
                    >
                        <section
                            ref={dialogRef}
                            id="knowledge-create-dialog"
                            className="modal-dialog knowledge-modal"
                            role="dialog"
                            aria-modal="true"
                            aria-labelledby="knowledge-create-title"
                            aria-describedby="knowledge-create-description"
                            aria-busy={creating}
                        >
                            <header className="modal-heading">
                                <div>
                                    <p className="panel-kicker">
                                        Knowledge base
                                    </p>
                                    <h2 id="knowledge-create-title">
                                        Create knowledge
                                    </h2>
                                    <p
                                        id="knowledge-create-description"
                                        className="panel-copy"
                                    >
                                        Add a durable source collection for
                                        grounded agent answers.
                                    </p>
                                </div>
                                <button
                                    ref={closeButtonRef}
                                    className="icon-button modal-close"
                                    type="button"
                                    aria-label="Close create knowledge dialog"
                                    disabled={creating}
                                    onClick={() => setCreateOpen(false)}
                                >
                                    <X size={16} aria-hidden="true" />
                                </button>
                            </header>

                            {error ? (
                                <div
                                    className="form-error knowledge-modal-error"
                                    role="alert"
                                >
                                    {error}
                                </div>
                            ) : null}
                            {!workspace && !workspaceLoading ? (
                                <div
                                    className="form-error knowledge-modal-error"
                                    role="alert"
                                >
                                    No workspace is available. Create one in
                                    Settings first.
                                </div>
                            ) : null}

                            <form
                                className="modal-form knowledge-modal-form"
                                onSubmit={(event) => {
                                    event.preventDefault();
                                    void create();
                                }}
                            >
                                <label
                                    className="knowledge-modal-field"
                                    htmlFor="knowledge-modal-name"
                                >
                                    <span>Name</span>
                                    <input
                                        id="knowledge-modal-name"
                                        value={name}
                                        onChange={(event) => {
                                            setName(event.target.value);
                                            if (error) setError(null);
                                        }}
                                        placeholder="Product documentation"
                                        autoComplete="off"
                                        maxLength={120}
                                        required
                                    />
                                </label>
                                <label
                                    className="knowledge-modal-field"
                                    htmlFor="knowledge-modal-description"
                                >
                                    <span>
                                        Description <em>(optional)</em>
                                    </span>
                                    <textarea
                                        id="knowledge-modal-description"
                                        value={description}
                                        onChange={(event) =>
                                            setDescription(event.target.value)
                                        }
                                        placeholder="What should agents know?"
                                        maxLength={500}
                                        rows={4}
                                    />
                                </label>
                                <p className="field-helper">
                                    You can upload PDF, UTF-8 TXT or Markdown
                                    files after creation.
                                </p>
                                <div className="modal-actions">
                                    <button
                                        className="button secondary-button"
                                        type="button"
                                        disabled={creating}
                                        onClick={() => setCreateOpen(false)}
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        className="button primary-button"
                                        type="submit"
                                        disabled={
                                            creating ||
                                            workspaceLoading ||
                                            !workspace ||
                                            !name.trim()
                                        }
                                    >
                                        {creating ? (
                                            <>
                                                <LoaderCircle
                                                    className="spin"
                                                    size={15}
                                                    aria-hidden="true"
                                                />
                                                Creating…
                                            </>
                                        ) : (
                                            <>
                                                <Plus
                                                    size={15}
                                                    aria-hidden="true"
                                                />
                                                Create knowledge
                                            </>
                                        )}
                                    </button>
                                </div>
                            </form>
                        </section>
                    </div>
                ) : null}
            </div>
        </AppShell>
    );
}
