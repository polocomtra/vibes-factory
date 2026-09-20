"use client";

import {
    AlertCircle,
    ArrowUpRight,
    Check,
    CheckCircle2,
    Code2,
    ChevronDown,
    FlaskConical,
    Globe2,
    KeyRound,
    LayoutGrid,
    List,
    LoaderCircle,
    Network,
    Plus,
    Search,
    ShieldCheck,
    X,
    Zap,
} from "lucide-react";
import {
    useEffect,
    useMemo,
    useRef,
    useState,
    type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { AppShell } from "../../components/app-shell";
import { DeleteAction } from "../../components/delete-action";
import { PaginationControls } from "../../components/pagination-controls";
import { apiFetch, readApiError } from "../../lib/api";
import { fetchCredentials, type Credential } from "../../lib/credentials";
import {
    createTool,
    createToolVersion,
    deleteTool,
    fetchToolVersion,
    fetchTools,
    testTool,
    type Tool,
    type ToolTestResult,
    type ToolVersionDetail,
} from "../../lib/tools";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };
type ViewMode = "grid" | "list";
type ToolFilter = "ALL" | "BUILT_IN" | "HTTP" | "MCP";

const TOOL_CARD_DESCRIPTION_LIMIT = 100;

function toolCardDescription(description: string | null) {
    const value = description?.trim() || "No description yet.";
    return value.length > TOOL_CARD_DESCRIPTION_LIMIT
        ? `${value.slice(0, TOOL_CARD_DESCRIPTION_LIMIT).trimEnd()}...`
        : value;
}

function providerLabel(tool: Tool) {
    if (tool.slug === "web_search") return "Exa";
    if (tool.type === "FUNCTION") return "Native";
    if (tool.type === "MCP") return "MCP server";
    return "HTTP";
}

function toolIcon(tool: Tool, size = 19) {
    return tool.slug === "web_search" ? (
        <Globe2 size={size} aria-hidden="true" />
    ) : (
        <Zap size={size} aria-hidden="true" />
    );
}

function ToolKindBadge({ tool }: { tool: Tool }) {
    if (tool.built_in) {
        return <span className="tool-kind-badge built-in-badge">Built-in</span>;
    }
    if (tool.type === "HTTP") {
        return (
            <span className="tool-kind-badge http-tool-badge">
                <Globe2 size={11} aria-hidden="true" />
                HTTP tool
            </span>
        );
    }
    if (tool.type === "MCP") {
        return (
            <span className="tool-kind-badge http-tool-badge">
                <Network size={11} aria-hidden="true" />
                MCP tool
            </span>
        );
    }
    return null;
}

function ToolCard({
    tool,
    onOpen,
    onDelete,
}: {
    tool: Tool;
    onOpen: (tool: Tool) => void;
    onDelete: (tool: Tool) => Promise<void>;
}) {
    const [confirmingDelete, setConfirmingDelete] = useState(false);
    const [deleting, setDeleting] = useState(false);

    async function handleDelete() {
        setDeleting(true);
        try {
            await onDelete(tool);
            setConfirmingDelete(false);
        } finally {
            setDeleting(false);
        }
    }

    return (
        <article className="tool-agent-card">
            <button
                className="tool-agent-card-main"
                type="button"
                onClick={() => onOpen(tool)}
            >
                <div className="tool-agent-card-top">
                    <span className="tool-agent-icon">{toolIcon(tool)}</span>
                    <span
                        className={
                            "status-badge " +
                            (tool.status === "ACTIVE" ? "success" : "muted")
                        }
                    >
                        <span />
                        {tool.status === "ACTIVE" ? "Active" : "Archived"}
                    </span>
                </div>
                <div className="tool-agent-card-title">
                    <h2>{tool.name}</h2>
                    <ToolKindBadge tool={tool} />
                </div>
                <p>{toolCardDescription(tool.description)}</p>
                <div className="tool-agent-card-meta">
                    <span>
                        <small>Provider</small>
                        <b>{providerLabel(tool)}</b>
                    </span>
                    <span>
                        <small>Type</small>
                        <code>{tool.type}</code>
                    </span>
                    <span>
                        <small>Version</small>
                        <b>v{tool.latest_version_number}</b>
                    </span>
                </div>
            </button>
            <footer>
                <span>
                    {tool.slug === "web_search"
                        ? "Test available"
                        : "Inspect schemas"}
                </span>
                <div className="card-footer-actions">
                    <ArrowUpRight size={15} aria-hidden="true" />
                    {!tool.built_in ? (
                        <DeleteAction
                            label={tool.name}
                            confirming={confirmingDelete}
                            busy={deleting}
                            onRequest={() => setConfirmingDelete(true)}
                            onCancel={() => setConfirmingDelete(false)}
                            onConfirm={() => void handleDelete()}
                        />
                    ) : null}
                </div>
            </footer>
        </article>
    );
}

type MCPToolGroup = {
    id: string;
    name: string;
    tools: Tool[];
};

function MCPServerGroupCard({
    group,
    onOpen,
}: {
    group: MCPToolGroup;
    onOpen: (group: MCPToolGroup) => void;
}) {
    return (
        <button
            className="tool-agent-card mcp-server-group-card"
            type="button"
            onClick={() => onOpen(group)}
        >
            <div className="tool-agent-card-top">
                <span className="tool-agent-icon mcp-group-icon">
                    <Network size={19} aria-hidden="true" />
                </span>
                <span className="status-badge success">
                    <span />
                    Imported
                </span>
            </div>
            <div className="tool-agent-card-title">
                <h2>{group.name}</h2>
                <span className="tool-kind-badge http-tool-badge">
                    <Network size={11} aria-hidden="true" /> MCP server
                </span>
            </div>
            <p>
                {group.tools.length} imported MCP{" "}
                {group.tools.length === 1 ? "tool" : "tools"} ready to use.
            </p>
            <div className="tool-agent-card-meta">
                <span>
                    <small>Provider</small>
                    <b>MCP server</b>
                </span>
                <span>
                    <small>Tools</small>
                    <b>{group.tools.length}</b>
                </span>
                <span>
                    <small>Versions</small>
                    <b>
                        {
                            new Set(
                                group.tools.map(
                                    (tool) => tool.latest_version_number,
                                ),
                            ).size
                        }
                    </b>
                </span>
            </div>
            <footer>
                <span>Open imported tools</span>
                <ArrowUpRight size={15} aria-hidden="true" />
            </footer>
        </button>
    );
}

function MCPToolsModal({
    group,
    onClose,
    onInspect,
    onDelete,
}: {
    group: MCPToolGroup;
    onClose: () => void;
    onInspect: (tool: Tool) => void;
    onDelete: (tool: Tool) => Promise<void>;
}) {
    const closeButtonRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        closeButtonRef.current?.focus();
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") onClose();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener("keydown", onKeyDown);
        };
    }, [onClose]);

    return (
        <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
                if (event.target === event.currentTarget) onClose();
            }}
        >
            <section
                className="modal-dialog tools-mcp-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="tools-mcp-modal-title"
            >
                <header className="modal-heading">
                    <div>
                        <p className="panel-kicker">MCP SERVER</p>
                        <h2 id="tools-mcp-modal-title">{group.name}</h2>
                        <p className="panel-copy">
                            {group.tools.length} imported tool
                            {group.tools.length === 1 ? "" : "s"}. Select one to
                            inspect its immutable schema.
                        </p>
                    </div>
                    <button
                        ref={closeButtonRef}
                        className="icon-button modal-close"
                        type="button"
                        aria-label="Close MCP tools"
                        onClick={onClose}
                    >
                        <X size={16} aria-hidden="true" />
                    </button>
                </header>
                <div
                    className="tools-mcp-list"
                    role="list"
                    aria-label={`${group.name} imported tools`}
                >
                    {group.tools.map((tool) => (
                        <MCPToolListItem
                            key={tool.id}
                            tool={tool}
                            onInspect={onInspect}
                            onDelete={onDelete}
                        />
                    ))}
                </div>
            </section>
        </div>
    );
}

function MCPToolListItem({
    tool,
    onInspect,
    onDelete,
}: {
    tool: Tool;
    onInspect: (tool: Tool) => void;
    onDelete: (tool: Tool) => Promise<void>;
}) {
    const [confirmingDelete, setConfirmingDelete] = useState(false);
    const [deleting, setDeleting] = useState(false);

    async function handleDelete() {
        setDeleting(true);
        try {
            await onDelete(tool);
            setConfirmingDelete(false);
        } finally {
            setDeleting(false);
        }
    }

    return (
        <div className="tools-mcp-list-row-wrap" role="listitem">
            <button
                className="tools-mcp-list-row"
                type="button"
                onClick={() => onInspect(tool)}
            >
                <span className="tool-agent-icon mcp-group-row-icon">
                    <Zap size={16} aria-hidden="true" />
                </span>
                <span className="tools-mcp-list-copy">
                    <strong>{tool.name}</strong>
                    <code>{tool.slug}</code>
                    <span>{toolCardDescription(tool.description)}</span>
                </span>
                <span className="tools-mcp-list-meta">
                    v{tool.latest_version_number}
                    <ArrowUpRight size={15} aria-hidden="true" />
                </span>
            </button>
            <DeleteAction
                label={tool.name}
                confirming={confirmingDelete}
                busy={deleting}
                onRequest={() => setConfirmingDelete(true)}
                onCancel={() => setConfirmingDelete(false)}
                onConfirm={() => void handleDelete()}
            />
        </div>
    );
}

function SchemaBlock({
    title,
    schema,
}: {
    title: string;
    schema: Record<string, unknown> | null | undefined;
}) {
    const properties = schema?.properties;
    const required = new Set(
        Array.isArray(schema?.required)
            ? schema.required.filter(
                  (item): item is string => typeof item === "string",
              )
            : [],
    );
    const fields =
        properties &&
        typeof properties === "object" &&
        !Array.isArray(properties)
            ? Object.entries(properties as Record<string, unknown>)
            : [];
    return (
        <section className="tool-schema-block" aria-label={title}>
            <header className="tool-schema-block-heading">
                <span>{title}</span>
                <span className="tool-schema-field-count">
                    {schema === undefined
                        ? "Loading…"
                        : `${fields.length} ${fields.length === 1 ? "field" : "fields"}`}
                </span>
                <Code2 size={14} aria-hidden="true" />
            </header>
            {schema === undefined ? (
                <div className="tool-schema-empty">Loading fields…</div>
            ) : fields.length === 0 ? (
                <div className="tool-schema-empty">No fields defined.</div>
            ) : (
                <div className="tool-schema-fields">
                    {fields.map(([name, definition]) => {
                        const field =
                            definition &&
                            typeof definition === "object" &&
                            !Array.isArray(definition)
                                ? (definition as Record<string, unknown>)
                                : {};
                        const fieldType = Array.isArray(field.type)
                            ? field.type
                                  .filter(
                                      (item): item is string =>
                                          typeof item === "string",
                                  )
                                  .join(" / ")
                            : typeof field.type === "string"
                              ? field.type
                              : "any";
                        const isRequired = required.has(name);
                        return (
                            <div className="tool-schema-field" key={name}>
                                <code>{name}</code>
                                <span className="tool-schema-type">
                                    {fieldType}
                                </span>
                                <span
                                    className={
                                        "tool-schema-required " +
                                        (isRequired ? "required" : "optional")
                                    }
                                >
                                    <span aria-hidden="true" />
                                    {isRequired ? "Required" : "Optional"}
                                </span>
                            </div>
                        );
                    })}
                </div>
            )}
        </section>
    );
}

type CreateToolForm = {
    name: string;
    slug: string;
    description: string;
    endpoint: string;
    method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD";
    inputFields: SchemaField[];
    outputFields: SchemaField[];
    timeoutSeconds: string;
    riskLevel: "LOW" | "MEDIUM" | "HIGH";
    credentialId: string;
    credentialHeader: string;
    credentialPrefix: string;
};

type SchemaFieldType =
    | "string"
    | "integer"
    | "number"
    | "boolean"
    | "object"
    | "array";
type SchemaField = {
    id: string;
    name: string;
    type: SchemaFieldType;
    required: boolean;
};
type SchemaFieldSection = "inputFields" | "outputFields";
type CreateToolScalarField =
    | "name"
    | "slug"
    | "description"
    | "endpoint"
    | "method"
    | "timeoutSeconds"
    | "riskLevel";
type CreateToolField = CreateToolScalarField | SchemaFieldSection;

const initialCreateToolForm: CreateToolForm = {
    name: "",
    slug: "",
    description: "",
    endpoint: "",
    method: "GET",
    inputFields: [],
    outputFields: [],
    timeoutSeconds: "30",
    riskLevel: "LOW",
    credentialId: "",
    credentialHeader: "Authorization",
    credentialPrefix: "Bearer",
};

function schemaFromFields(fields: SchemaField[]): Record<string, unknown> {
    const properties: Record<string, unknown> = {};
    const required: string[] = [];
    for (const field of fields) {
        const name = field.name.trim();
        if (!name) continue;
        properties[name] = { type: field.type };
        if (field.required) required.push(name);
    }
    return {
        type: "object",
        properties,
        ...(required.length > 0 ? { required } : {}),
        additionalProperties: false,
    };
}

function schemaFieldId() {
    return `schema-field-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function fieldTypeLabel(type: SchemaFieldType) {
    return type === "integer"
        ? "Integer"
        : type.charAt(0).toUpperCase() + type.slice(1);
}

function SchemaFieldEditor({
    kind,
    fields,
    errors,
    onChange,
    onAdd,
    onRemove,
}: {
    kind: "input" | "output";
    fields: SchemaField[];
    errors: Record<string, string>;
    onChange: (id: string, changes: Partial<Omit<SchemaField, "id">>) => void;
    onAdd: () => void;
    onRemove: (id: string) => void;
}) {
    const title = kind === "input" ? "Input fields" : "Output fields";
    return (
        <div className="schema-field-editor">
            <div className="schema-field-editor-heading">
                <div>
                    <h4>{title}</h4>
                    <p>
                        {kind === "input"
                            ? "Arguments the tool can receive."
                            : "Fields returned by the endpoint."}
                    </p>
                </div>
                <span>
                    {fields.length} {fields.length === 1 ? "field" : "fields"}
                </span>
            </div>
            {fields.length > 0 ? (
                <div className="schema-field-list">
                    {fields.map((field) => (
                        <div className="schema-field-row" key={field.id}>
                            <label
                                className="schema-field-name"
                                htmlFor={`${kind}-field-name-${field.id}`}
                            >
                                Field name
                                <input
                                    id={`${kind}-field-name-${field.id}`}
                                    value={field.name}
                                    placeholder="userId"
                                    onChange={(event) =>
                                        onChange(field.id, {
                                            name: event.target.value,
                                        })
                                    }
                                    aria-invalid={Boolean(errors[field.id])}
                                />
                                {errors[field.id] ? (
                                    <span className="create-tool-field-error">
                                        {errors[field.id]}
                                    </span>
                                ) : null}
                            </label>
                            <label htmlFor={`${kind}-field-type-${field.id}`}>
                                Type
                                <select
                                    id={`${kind}-field-type-${field.id}`}
                                    value={field.type}
                                    onChange={(event) =>
                                        onChange(field.id, {
                                            type: event.target
                                                .value as SchemaFieldType,
                                        })
                                    }
                                >
                                    {(
                                        [
                                            "string",
                                            "integer",
                                            "number",
                                            "boolean",
                                            "object",
                                            "array",
                                        ] as SchemaFieldType[]
                                    ).map((type) => (
                                        <option key={type} value={type}>
                                            {fieldTypeLabel(type)}
                                        </option>
                                    ))}
                                </select>
                            </label>
                            <label
                                className="schema-required-toggle"
                                htmlFor={`${kind}-field-required-${field.id}`}
                            >
                                <input
                                    id={`${kind}-field-required-${field.id}`}
                                    type="checkbox"
                                    checked={field.required}
                                    onChange={(event) =>
                                        onChange(field.id, {
                                            required: event.target.checked,
                                        })
                                    }
                                />
                                <span>
                                    {field.required ? "Required" : "Optional"}
                                </span>
                            </label>
                            <button
                                className="icon-button schema-field-remove"
                                type="button"
                                onClick={() => onRemove(field.id)}
                                aria-label={`Remove ${field.name || "unnamed"} field`}
                            >
                                <X size={15} aria-hidden="true" />
                            </button>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="schema-field-empty">
                    No fields yet. Add one to define the tool contract.
                </div>
            )}
            <button
                className="button secondary-button schema-add-field"
                type="button"
                onClick={onAdd}
            >
                <Plus size={14} aria-hidden="true" />
                Add field
            </button>
        </div>
    );
}

function slugify(value: string) {
    return value
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 100);
}

function CredentialSelect({
    credentials,
    value,
    loading,
    labelId,
    helpId,
    onChange,
}: {
    credentials: Credential[];
    value: string;
    loading: boolean;
    labelId: string;
    helpId: string;
    onChange: (value: string) => void;
}) {
    const options = useMemo(
        () => [
            {
                id: "",
                name: "No credential",
                detail: "Leave this request unauthenticated",
                provider: "",
                type: "",
            },
            ...credentials.map((credential) => ({
                id: credential.id,
                name: credential.name,
                detail: `${credential.provider} · ${credential.type}`,
                provider: credential.provider,
                type: credential.type,
            })),
        ],
        [credentials],
    );
    const selectedIndex = Math.max(
        0,
        options.findIndex((option) => option.id === value),
    );
    const selected = options[selectedIndex] ?? options[0];
    const [open, setOpen] = useState(false);
    const [activeIndex, setActiveIndex] = useState(selectedIndex);
    const wrapperRef = useRef<HTMLDivElement>(null);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const listboxId = "create-tool-credential-listbox";

    useEffect(() => {
        if (!open) return;
        setActiveIndex(selectedIndex);
        function dismiss(event: PointerEvent) {
            if (!wrapperRef.current?.contains(event.target as Node)) {
                setOpen(false);
            }
        }
        document.addEventListener("pointerdown", dismiss);
        return () => document.removeEventListener("pointerdown", dismiss);
    }, [open, selectedIndex]);

    useEffect(() => {
        if (!open) return;
        document
            .getElementById(`${listboxId}-option-${activeIndex}`)
            ?.scrollIntoView({
                block: "nearest",
            });
    }, [activeIndex, listboxId, open]);

    function choose(index: number) {
        const option = options[index];
        if (!option) return;
        onChange(option.id);
        setOpen(false);
        window.requestAnimationFrame(() => triggerRef.current?.focus());
    }

    function handleKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
        if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((current) =>
                Math.min(current + 1, options.length - 1),
            );
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((current) => Math.max(current - 1, 0));
        } else if (event.key === "Home" && open) {
            event.preventDefault();
            setActiveIndex(0);
        } else if (event.key === "End" && open) {
            event.preventDefault();
            setActiveIndex(options.length - 1);
        } else if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            if (open) choose(activeIndex);
            else {
                setOpen(true);
                setActiveIndex(selectedIndex);
            }
        } else if (event.key === "Escape" && open) {
            event.preventDefault();
            setOpen(false);
        }
    }

    return (
        <div ref={wrapperRef} className="credential-combobox">
            <button
                ref={triggerRef}
                className="credential-combobox-trigger"
                type="button"
                role="combobox"
                aria-labelledby={labelId}
                aria-describedby={helpId}
                aria-controls={listboxId}
                aria-expanded={open}
                aria-activedescendant={
                    open ? `${listboxId}-option-${activeIndex}` : undefined
                }
                aria-busy={loading}
                disabled={loading}
                onClick={() => {
                    setOpen((current) => !current);
                    setActiveIndex(selectedIndex);
                }}
                onKeyDown={handleKeyDown}
            >
                <span className="credential-trigger-leading" aria-hidden="true">
                    <KeyRound size={15} />
                </span>
                <span className="credential-trigger-copy">
                    <strong>{selected?.name ?? "No credential"}</strong>
                    <small>
                        {selected?.detail ??
                            "Leave this request unauthenticated"}
                    </small>
                </span>
                <ChevronDown
                    className={
                        open ? "credential-chevron open" : "credential-chevron"
                    }
                    size={16}
                    aria-hidden="true"
                />
            </button>
            {open ? (
                <ul
                    id={listboxId}
                    className="credential-combobox-listbox"
                    role="listbox"
                    aria-labelledby={labelId}
                >
                    {options.map((option, index) => (
                        <li
                            id={`${listboxId}-option-${index}`}
                            className={
                                index === activeIndex
                                    ? "credential-combobox-option active"
                                    : "credential-combobox-option"
                            }
                            key={option.id || "none"}
                            role="option"
                            aria-selected={option.id === value}
                            onMouseDown={(event) => event.preventDefault()}
                            onMouseEnter={() => setActiveIndex(index)}
                            onClick={() => choose(index)}
                        >
                            <span className="credential-option-copy">
                                <strong>{option.name}</strong>
                                <small>{option.detail}</small>
                            </span>
                            {option.id === value ? (
                                <Check
                                    className="credential-option-check"
                                    size={15}
                                    aria-hidden="true"
                                />
                            ) : null}
                        </li>
                    ))}
                </ul>
            ) : null}
        </div>
    );
}

function CreateToolModal({
    workspaceId,
    onClose,
    onCreated,
}: {
    workspaceId: string;
    onClose: () => void;
    onCreated: () => Promise<void> | void;
}) {
    const [form, setForm] = useState<CreateToolForm>(initialCreateToolForm);
    const [fieldErrors, setFieldErrors] = useState<
        Partial<Record<CreateToolField, string>>
    >({});
    const [error, setError] = useState<string | null>(null);
    const [creating, setCreating] = useState(false);
    const [credentials, setCredentials] = useState<Credential[]>([]);
    const [credentialsLoading, setCredentialsLoading] = useState(false);
    const [versionSetupFailed, setVersionSetupFailed] = useState(false);
    const [schemaErrors, setSchemaErrors] = useState<
        Record<SchemaFieldSection, Record<string, string>>
    >({ inputFields: {}, outputFields: {} });
    const [slugTouched, setSlugTouched] = useState(false);
    const closeButtonRef = useRef<HTMLButtonElement>(null);
    const errorSummaryRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const focusFrame = window.requestAnimationFrame(() =>
            closeButtonRef.current?.focus(),
        );
        function closeOnEscape(event: KeyboardEvent) {
            if (event.key === "Escape" && !creating) onClose();
        }
        window.addEventListener("keydown", closeOnEscape);
        return () => {
            window.cancelAnimationFrame(focusFrame);
            window.removeEventListener("keydown", closeOnEscape);
            document.body.style.overflow = previousOverflow;
        };
    }, [creating, onClose]);

    useEffect(() => {
        let active = true;
        setCredentialsLoading(true);
        void fetchCredentials(workspaceId)
            .then((items) => {
                if (active)
                    setCredentials(
                        items.filter((item) => item.status === "ACTIVE"),
                    );
            })
            .catch(() => {
                if (active) setCredentials([]);
            })
            .finally(() => {
                if (active) setCredentialsLoading(false);
            });
        return () => {
            active = false;
        };
    }, [workspaceId]);

    function updateField(field: CreateToolScalarField, value: string) {
        setForm((current) => ({ ...current, [field]: value }));
        setFieldErrors((current) => ({ ...current, [field]: undefined }));
        setError(null);
    }

    function validateField(field: CreateToolScalarField, currentForm = form) {
        let message: string | undefined;
        const value = currentForm[field];
        if (field === "name" && !value.trim()) message = "Enter a tool name.";
        if (field === "name" && value.length > 255)
            message = "Use 255 characters or fewer.";
        if (field === "slug" && !/^[a-z0-9][a-z0-9_-]*$/.test(value))
            message = "Use lowercase letters, numbers, hyphens or underscores.";
        if (field === "endpoint") {
            try {
                const url = new URL(value.trim());
                if (!["http:", "https:"].includes(url.protocol))
                    message = "Use an http:// or https:// endpoint.";
            } catch {
                message = "Enter a valid HTTP endpoint URL.";
            }
        }
        if (field === "timeoutSeconds") {
            const timeout = Number(value);
            if (!Number.isInteger(timeout) || timeout < 1 || timeout > 3600)
                message = "Use a whole number from 1 to 3600 seconds.";
        }
        setFieldErrors((current) => ({ ...current, [field]: message }));
        return message;
    }

    function updateSchemaField(
        section: SchemaFieldSection,
        id: string,
        changes: Partial<Omit<SchemaField, "id">>,
    ) {
        setForm((current) => ({
            ...current,
            [section]: current[section].map((field) =>
                field.id === id ? { ...field, ...changes } : field,
            ),
        }));
        setSchemaErrors((current) => ({
            ...current,
            [section]: { ...current[section], [id]: "" },
        }));
        setError(null);
    }

    function validateSchemaFields(fields: SchemaField[]) {
        const errors: Record<string, string> = {};
        const seen = new Set<string>();
        for (const field of fields) {
            const name = field.name.trim();
            const normalized = name.toLowerCase();
            if (!name) errors[field.id] = "Enter a field name.";
            else if (name.length > 100)
                errors[field.id] = "Use 100 characters or fewer.";
            else if (seen.has(normalized))
                errors[field.id] = "Field names must be unique.";
            else seen.add(normalized);
        }
        return errors;
    }

    function addSchemaField(section: SchemaFieldSection) {
        setForm((current) => ({
            ...current,
            [section]: [
                ...current[section],
                {
                    id: schemaFieldId(),
                    name: "",
                    type: "string",
                    required: false,
                },
            ],
        }));
        setError(null);
    }

    function removeSchemaField(section: SchemaFieldSection, id: string) {
        setForm((current) => ({
            ...current,
            [section]: current[section].filter((field) => field.id !== id),
        }));
        setSchemaErrors((current) => {
            const next = { ...current[section] };
            delete next[id];
            return { ...current, [section]: next };
        });
    }

    function validateForm() {
        const fields: CreateToolScalarField[] = ["name", "slug", "endpoint"];
        const nextErrors: Partial<Record<CreateToolField, string>> = {};
        for (const field of fields) {
            const message = validateField(field, form);
            if (message) nextErrors[field] = message;
        }
        const timeout = Number(form.timeoutSeconds);
        if (!Number.isInteger(timeout) || timeout < 1 || timeout > 3600)
            nextErrors.timeoutSeconds =
                "Use a whole number from 1 to 3600 seconds.";
        const nextSchemaErrors = {
            inputFields: validateSchemaFields(form.inputFields),
            outputFields: validateSchemaFields(form.outputFields),
        };
        setSchemaErrors(nextSchemaErrors);
        if (Object.keys(nextSchemaErrors.inputFields).length > 0)
            nextErrors.inputFields = "Fix the highlighted input fields.";
        if (Object.keys(nextSchemaErrors.outputFields).length > 0)
            nextErrors.outputFields = "Fix the highlighted output fields.";
        setFieldErrors(nextErrors);
        return nextErrors;
    }

    async function submit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const errors = validateForm();
        if (Object.keys(errors).length > 0) {
            window.requestAnimationFrame(() =>
                errorSummaryRef.current?.focus(),
            );
            return;
        }
        setCreating(true);
        setError(null);
        try {
            const tool = await createTool(workspaceId, {
                name: form.name.trim(),
                slug: form.slug.trim(),
                description: form.description.trim() || null,
                type: "HTTP",
            });
            try {
                await createToolVersion(tool.id, {
                    name: form.name.trim(),
                    description: form.description.trim() || null,
                    input_schema: schemaFromFields(form.inputFields),
                    output_schema:
                        form.outputFields.length > 0
                            ? schemaFromFields(form.outputFields)
                            : null,
                    executor: {
                        type: "HTTP",
                        config: {
                            method: form.method,
                            base_url: (() => {
                                const endpoint = new URL(form.endpoint.trim());
                                return endpoint.origin;
                            })(),
                            path: (() => {
                                const endpoint = new URL(form.endpoint.trim());
                                return endpoint.pathname + endpoint.search;
                            })(),
                            headers: {},
                            query_mapping: {},
                            body_mapping: {},
                            ...(form.credentialId
                                ? {
                                      credential_ref: form.credentialId,
                                      credential_binding: {
                                          location: "HEADER",
                                          name:
                                              form.credentialHeader.trim() ||
                                              "Authorization",
                                          prefix: form.credentialPrefix.trim(),
                                          secret_key: "token",
                                      },
                                  }
                                : {}),
                        },
                    },
                    timeout_seconds: Number(form.timeoutSeconds),
                    retry_policy: {},
                    risk_level: form.riskLevel,
                    side_effect: false,
                    idempotent: form.method === "GET" || form.method === "HEAD",
                });
            } catch (reason: unknown) {
                setVersionSetupFailed(true);
                setError(
                    "The tool was created, but its first HTTP version could not be created. Refresh the catalog before trying again.",
                );
                return;
            }
            await onCreated();
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Unable to create the HTTP tool.",
            );
        } finally {
            setCreating(false);
        }
    }

    const errorEntries = Object.entries(fieldErrors).filter(
        (entry): entry is [CreateToolField, string] => Boolean(entry[1]),
    );
    const selectedCredential = credentials.find(
        (credential) => credential.id === form.credentialId,
    );
    return (
        <div
            className="modal-backdrop tool-modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
                if (event.target === event.currentTarget && !creating)
                    onClose();
            }}
        >
            <section
                className="modal-dialog create-tool-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="create-tool-title"
                aria-describedby="create-tool-description"
            >
                <header className="modal-heading">
                    <div>
                        <p className="panel-kicker">Tool catalog</p>
                        <h2 id="create-tool-title">Create HTTP tool</h2>
                        <p id="create-tool-description" className="panel-copy">
                            Add a public HTTP endpoint as an immutable,
                            versioned capability.
                        </p>
                    </div>
                    <button
                        ref={closeButtonRef}
                        className="icon-button modal-close"
                        type="button"
                        aria-label="Close create tool dialog"
                        onClick={onClose}
                        disabled={creating}
                    >
                        <X size={16} aria-hidden="true" />
                    </button>
                </header>
                <div className="create-tool-callout">
                    <Globe2 size={15} aria-hidden="true" />
                    <span>
                        <strong>HTTP only · public endpoint</strong> Credentials
                        are resolved server-side and never sent to the model.
                    </span>
                </div>
                {errorEntries.length > 0 ? (
                    <div
                        ref={errorSummaryRef}
                        className="create-tool-error-summary"
                        role="alert"
                        tabIndex={-1}
                    >
                        <strong>Check the highlighted fields.</strong>
                        <ul>
                            {errorEntries.map(([field, message]) => (
                                <li key={field}>
                                    <a
                                        href={
                                            field === "inputFields"
                                                ? "#create-tool-input-fields"
                                                : field === "outputFields"
                                                  ? "#create-tool-output-fields"
                                                  : `#create-tool-${field}`
                                        }
                                    >
                                        {message}
                                    </a>
                                </li>
                            ))}
                        </ul>
                    </div>
                ) : null}
                <section
                    className="create-tool-section credential-injection-section"
                    aria-labelledby="credential-injection-title"
                >
                    <div className="tool-modal-section-heading credential-injection-heading">
                        <div>
                            <div className="credential-heading-line">
                                <p className="panel-kicker">
                                    Optional authentication
                                </p>
                                <span className="credential-optional-badge">
                                    Optional
                                </span>
                            </div>
                            <h3 id="credential-injection-title">
                                Credential injection
                            </h3>
                            <p className="credential-section-copy">
                                Bind a workspace vault entry to one HTTP header.
                                The secret is resolved only when this tool
                                executes.
                            </p>
                        </div>
                        <span
                            className="credential-security-icon"
                            aria-hidden="true"
                        >
                            <ShieldCheck size={18} />
                        </span>
                    </div>

                    <div className="credential-field">
                        <span
                            id="create-tool-credential-label"
                            className="credential-field-label"
                        >
                            Credential
                        </span>
                        <CredentialSelect
                            credentials={credentials}
                            value={form.credentialId}
                            loading={credentialsLoading}
                            labelId="create-tool-credential-label"
                            helpId="create-tool-credential-help"
                            onChange={(value) =>
                                setForm((current) => ({
                                    ...current,
                                    credentialId: value,
                                }))
                            }
                        />
                        <span
                            id="create-tool-credential-help"
                            className="field-helper"
                        >
                            {credentialsLoading
                                ? "Loading active credentials…"
                                : credentials.length === 0
                                  ? "No active credentials found. Add one in Settings → Credentials."
                                  : "Choose an active credential. Secret values never leave the backend."}
                        </span>
                    </div>

                    {selectedCredential ? (
                        <>
                            <div
                                className="credential-selection-card"
                                role="status"
                                aria-live="polite"
                            >
                                <span
                                    className="credential-selection-icon"
                                    aria-hidden="true"
                                >
                                    <KeyRound size={16} />
                                </span>
                                <span className="credential-selection-copy">
                                    <strong>{selectedCredential.name}</strong>
                                    <span>
                                        {selectedCredential.provider} ·{" "}
                                        {selectedCredential.type}
                                    </span>
                                </span>
                                <span className="credential-secret-badge">
                                    <ShieldCheck size={13} aria-hidden="true" />
                                    Server-side only
                                </span>
                            </div>

                            <div className="create-tool-field-grid credential-binding-grid">
                                <label
                                    className="credential-field"
                                    htmlFor="create-tool-credential-header"
                                >
                                    <span className="credential-field-label">
                                        Header name
                                    </span>
                                    <input
                                        id="create-tool-credential-header"
                                        value={form.credentialHeader}
                                        onChange={(event) =>
                                            setForm((current) => ({
                                                ...current,
                                                credentialHeader:
                                                    event.target.value,
                                            }))
                                        }
                                        placeholder="Authorization"
                                        autoComplete="off"
                                        aria-describedby="create-tool-credential-header-help"
                                    />
                                    <span
                                        id="create-tool-credential-header-help"
                                        className="field-helper"
                                    >
                                        Where the token is attached.
                                    </span>
                                </label>
                                <label
                                    className="credential-field"
                                    htmlFor="create-tool-credential-prefix"
                                >
                                    <span className="credential-field-label">
                                        Prefix
                                    </span>
                                    <input
                                        id="create-tool-credential-prefix"
                                        value={form.credentialPrefix}
                                        onChange={(event) =>
                                            setForm((current) => ({
                                                ...current,
                                                credentialPrefix:
                                                    event.target.value,
                                            }))
                                        }
                                        placeholder="Bearer"
                                        autoComplete="off"
                                        aria-describedby="create-tool-credential-prefix-help"
                                    />
                                    <span
                                        id="create-tool-credential-prefix-help"
                                        className="field-helper"
                                    >
                                        Leave empty for no prefix.
                                    </span>
                                </label>
                            </div>

                            <div
                                className="credential-header-preview"
                                aria-label="Runtime header preview"
                            >
                                <div className="credential-header-preview-heading">
                                    <span>Runtime header</span>
                                    <span>Injected on execute</span>
                                </div>
                                <code>
                                    {form.credentialHeader.trim() ||
                                        "Authorization"}
                                    :{" "}
                                    {form.credentialPrefix.trim()
                                        ? `${form.credentialPrefix.trim()} `
                                        : ""}
                                    <span>••••••••</span>
                                </code>
                            </div>
                        </>
                    ) : (
                        <div className="credential-unselected-note">
                            <KeyRound size={15} aria-hidden="true" />
                            <span>
                                Select a credential to enable secure header
                                injection.
                            </span>
                        </div>
                    )}
                </section>
                {error ? (
                    <div className="form-error tool-modal-alert" role="alert">
                        <AlertCircle size={15} aria-hidden="true" />
                        {error}
                    </div>
                ) : null}
                <form
                    className="create-tool-form"
                    onSubmit={(event) => void submit(event)}
                    aria-busy={creating}
                    noValidate
                >
                    <div className="create-tool-section">
                        <div className="tool-modal-section-heading">
                            <div>
                                <p className="panel-kicker">Identity</p>
                                <h3>Tool details</h3>
                            </div>
                            <Zap size={17} aria-hidden="true" />
                        </div>
                        <div className="create-tool-field-grid">
                            <label htmlFor="create-tool-name">
                                Name
                                <input
                                    id="create-tool-name"
                                    value={form.name}
                                    maxLength={255}
                                    onChange={(event) => {
                                        const value = event.target.value;
                                        updateField("name", value);
                                        if (!slugTouched)
                                            setForm((current) => ({
                                                ...current,
                                                slug: slugify(value),
                                            }));
                                    }}
                                    onBlur={() => validateField("name")}
                                    aria-invalid={Boolean(fieldErrors.name)}
                                    aria-describedby={
                                        fieldErrors.name
                                            ? "create-tool-name-error"
                                            : undefined
                                    }
                                />
                                {fieldErrors.name ? (
                                    <span
                                        id="create-tool-name-error"
                                        className="create-tool-field-error"
                                    >
                                        {fieldErrors.name}
                                    </span>
                                ) : null}
                            </label>
                            <label htmlFor="create-tool-slug">
                                Slug
                                <input
                                    id="create-tool-slug"
                                    value={form.slug}
                                    onChange={(event) => {
                                        setSlugTouched(true);
                                        updateField("slug", event.target.value);
                                    }}
                                    onBlur={() => validateField("slug")}
                                    aria-invalid={Boolean(fieldErrors.slug)}
                                    aria-describedby={
                                        fieldErrors.slug
                                            ? "create-tool-slug-error"
                                            : undefined
                                    }
                                />
                                {fieldErrors.slug ? (
                                    <span
                                        id="create-tool-slug-error"
                                        className="create-tool-field-error"
                                    >
                                        {fieldErrors.slug}
                                    </span>
                                ) : null}
                            </label>
                        </div>
                        <label htmlFor="create-tool-description">
                            Description
                            <span className="create-tool-label-hint">
                                Optional
                            </span>
                            <textarea
                                id="create-tool-description"
                                value={form.description}
                                maxLength={1000}
                                rows={2}
                                onChange={(event) =>
                                    updateField(
                                        "description",
                                        event.target.value,
                                    )
                                }
                            />
                        </label>
                    </div>

                    <div className="create-tool-section">
                        <div className="tool-modal-section-heading">
                            <div>
                                <p className="panel-kicker">Runtime target</p>
                                <h3>HTTP endpoint</h3>
                            </div>
                            <ArrowUpRight size={17} aria-hidden="true" />
                        </div>
                        <label htmlFor="create-tool-endpoint">
                            Endpoint URL
                            <input
                                id="create-tool-endpoint"
                                type="url"
                                value={form.endpoint}
                                placeholder="https://api.example.com/v1/resource"
                                onChange={(event) =>
                                    updateField("endpoint", event.target.value)
                                }
                                onBlur={() => validateField("endpoint")}
                                aria-invalid={Boolean(fieldErrors.endpoint)}
                                aria-describedby="create-tool-endpoint-help create-tool-endpoint-error"
                            />
                            {fieldErrors.endpoint ? (
                                <span
                                    id="create-tool-endpoint-error"
                                    className="create-tool-field-error"
                                >
                                    {fieldErrors.endpoint}
                                </span>
                            ) : null}
                            <span
                                id="create-tool-endpoint-help"
                                className="field-helper"
                            >
                                Public endpoint only. The request body/query
                                mapping follows the tool input arguments.
                            </span>
                        </label>
                        <div className="create-tool-field-grid">
                            <label htmlFor="create-tool-method">
                                Method
                                <select
                                    id="create-tool-method"
                                    value={form.method}
                                    onChange={(event) =>
                                        updateField(
                                            "method",
                                            event.target.value,
                                        )
                                    }
                                >
                                    <option>GET</option>
                                    <option>POST</option>
                                    <option>PUT</option>
                                    <option>PATCH</option>
                                    <option>DELETE</option>
                                    <option>HEAD</option>
                                </select>
                            </label>
                            <label htmlFor="create-tool-timeout">
                                Timeout (seconds)
                                <input
                                    id="create-tool-timeout"
                                    type="number"
                                    min={1}
                                    max={3600}
                                    step={1}
                                    value={form.timeoutSeconds}
                                    onChange={(event) =>
                                        updateField(
                                            "timeoutSeconds",
                                            event.target.value,
                                        )
                                    }
                                    onBlur={() =>
                                        validateField("timeoutSeconds")
                                    }
                                    aria-invalid={Boolean(
                                        fieldErrors.timeoutSeconds,
                                    )}
                                />
                                {fieldErrors.timeoutSeconds ? (
                                    <span className="create-tool-field-error">
                                        {fieldErrors.timeoutSeconds}
                                    </span>
                                ) : null}
                            </label>
                        </div>
                    </div>

                    <div className="create-tool-section">
                        <div className="tool-modal-section-heading">
                            <div>
                                <p className="panel-kicker">Runtime contract</p>
                                <h3>Schemas and policy</h3>
                            </div>
                            <Code2 size={17} aria-hidden="true" />
                        </div>
                        <div className="create-tool-schema-grid">
                            <div id="create-tool-input-fields">
                                <SchemaFieldEditor
                                    kind="input"
                                    fields={form.inputFields}
                                    errors={schemaErrors.inputFields}
                                    onChange={(id, changes) =>
                                        updateSchemaField(
                                            "inputFields",
                                            id,
                                            changes,
                                        )
                                    }
                                    onAdd={() => addSchemaField("inputFields")}
                                    onRemove={(id) =>
                                        removeSchemaField("inputFields", id)
                                    }
                                />
                                {fieldErrors.inputFields ? (
                                    <span className="create-tool-field-error">
                                        {fieldErrors.inputFields}
                                    </span>
                                ) : null}
                            </div>
                            <div id="create-tool-output-fields">
                                <SchemaFieldEditor
                                    kind="output"
                                    fields={form.outputFields}
                                    errors={schemaErrors.outputFields}
                                    onChange={(id, changes) =>
                                        updateSchemaField(
                                            "outputFields",
                                            id,
                                            changes,
                                        )
                                    }
                                    onAdd={() => addSchemaField("outputFields")}
                                    onRemove={(id) =>
                                        removeSchemaField("outputFields", id)
                                    }
                                />
                                {fieldErrors.outputFields ? (
                                    <span className="create-tool-field-error">
                                        {fieldErrors.outputFields}
                                    </span>
                                ) : null}
                            </div>
                        </div>
                        <div className="create-tool-field-grid">
                            <label htmlFor="create-tool-risk">
                                Risk level
                                <select
                                    id="create-tool-risk"
                                    value={form.riskLevel}
                                    onChange={(event) =>
                                        updateField(
                                            "riskLevel",
                                            event.target.value,
                                        )
                                    }
                                >
                                    <option>LOW</option>
                                    <option>MEDIUM</option>
                                    <option>HIGH</option>
                                </select>
                            </label>
                            <div className="create-tool-policy-note">
                                <ShieldCheck size={14} aria-hidden="true" />
                                <span>
                                    Side effects are marked off by default.
                                    Publish an agent version before runtime use.
                                </span>
                            </div>
                        </div>
                    </div>
                    <div className="modal-actions">
                        <button
                            className="button secondary-button"
                            type="button"
                            onClick={onClose}
                            disabled={creating}
                        >
                            Cancel
                        </button>
                        <button
                            className="button primary-button"
                            type="submit"
                            disabled={creating || versionSetupFailed}
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
                            ) : versionSetupFailed ? (
                                "Version setup incomplete"
                            ) : (
                                <>
                                    <Plus size={15} aria-hidden="true" />
                                    Create HTTP tool
                                </>
                            )}
                        </button>
                    </div>
                </form>
            </section>
        </div>
    );
}

function sampleValue(schema: unknown): unknown {
    if (!schema || typeof schema !== "object" || Array.isArray(schema))
        return null;
    const definition = schema as Record<string, unknown>;
    if (definition.default !== undefined) return definition.default;
    if (Array.isArray(definition.enum) && definition.enum.length > 0)
        return definition.enum[0];
    if (definition.type === "object" || definition.properties) {
        const properties = definition.properties;
        if (
            !properties ||
            typeof properties !== "object" ||
            Array.isArray(properties)
        )
            return {};
        return Object.fromEntries(
            Object.entries(properties as Record<string, unknown>).map(
                ([key, value]) => [key, sampleValue(value)],
            ),
        );
    }
    if (definition.type === "array") return [sampleValue(definition.items)];
    if (definition.type === "integer" || definition.type === "number") return 1;
    if (definition.type === "boolean") return false;
    return "sample";
}

function ToolDetailModal({
    tool,
    versionDetail,
    onClose,
}: {
    tool: Tool;
    versionDetail: ToolVersionDetail | null;
    onClose: () => void;
}) {
    const [query, setQuery] = useState("Latest news on Nvidia");
    const [numResults, setNumResults] = useState("10");
    const [argumentsText, setArgumentsText] = useState("{}\n");
    const [argumentsError, setArgumentsError] = useState<string | null>(null);
    const [testing, setTesting] = useState(false);
    const [result, setResult] = useState<ToolTestResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const closeButtonRef = useRef<HTMLButtonElement>(null);
    const httpTool = tool.type === "HTTP";
    const testable = httpTool || tool.slug === "web_search";

    useEffect(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const focusFrame = window.requestAnimationFrame(() =>
            closeButtonRef.current?.focus(),
        );
        function closeOnEscape(event: KeyboardEvent) {
            if (event.key === "Escape") onClose();
        }
        window.addEventListener("keydown", closeOnEscape);
        return () => {
            window.cancelAnimationFrame(focusFrame);
            window.removeEventListener("keydown", closeOnEscape);
            document.body.style.overflow = previousOverflow;
        };
    }, [onClose]);

    useEffect(() => {
        if (httpTool && versionDetail) {
            setArgumentsText(
                JSON.stringify(
                    sampleValue(versionDetail.input_schema),
                    null,
                    2,
                ) + "\n",
            );
            setArgumentsError(null);
        }
    }, [httpTool, versionDetail]);

    async function runTest(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!versionDetail) {
            setError("The immutable tool version is still loading.");
            return;
        }
        let arguments_: Record<string, unknown>;
        if (httpTool) {
            try {
                const parsed: unknown = JSON.parse(argumentsText);
                if (
                    !parsed ||
                    typeof parsed !== "object" ||
                    Array.isArray(parsed)
                )
                    throw new Error("Arguments must be a JSON object.");
                arguments_ = parsed as Record<string, unknown>;
            } catch (reason: unknown) {
                const message =
                    reason instanceof Error
                        ? reason.message
                        : "Enter a valid JSON object.";
                setArgumentsError(message);
                setError(null);
                return;
            }
        } else {
            if (!query.trim()) {
                setError("Enter a search query before testing.");
                return;
            }
            arguments_ = {
                query: query.trim(),
                num_results: Number(numResults),
            };
        }
        setArgumentsError(null);
        setError(null);
        setResult(null);
        setTesting(true);
        try {
            setResult(await testTool(versionDetail.id, arguments_));
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "The tool test failed.",
            );
        } finally {
            setTesting(false);
        }
    }

    return (
        <div
            className="modal-backdrop tool-modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
                if (event.target === event.currentTarget) onClose();
            }}
        >
            <section
                className="modal-dialog tool-detail-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="tool-detail-title"
                aria-describedby="tool-detail-description"
            >
                <header className="modal-heading">
                    <div>
                        <p className="panel-kicker">Tool detail</p>
                        <h2 id="tool-detail-title">{tool.name}</h2>
                        <p id="tool-detail-description" className="panel-copy">
                            {tool.description ||
                                "Inspect the immutable tool version and its runtime contract."}
                        </p>
                    </div>
                    <button
                        ref={closeButtonRef}
                        className="icon-button modal-close"
                        type="button"
                        aria-label="Close tool detail"
                        onClick={onClose}
                    >
                        <X size={16} aria-hidden="true" />
                    </button>
                </header>

                <div className="tool-modal-meta">
                    <span className="tool-agent-icon small">
                        {toolIcon(tool, 15)}
                    </span>
                    <span>
                        <small>Provider</small>
                        <b>{providerLabel(tool)}</b>
                    </span>
                    <span>
                        <small>Type</small>
                        <b>{tool.type}</b>
                    </span>
                    <span>
                        <small>Version</small>
                        <b>v{tool.latest_version_number}</b>
                    </span>
                    <ToolKindBadge tool={tool} />
                    <span
                        className={
                            "status-badge " +
                            (tool.status === "ACTIVE" ? "success" : "muted")
                        }
                    >
                        <span />
                        {tool.status === "ACTIVE" ? "Active" : "Archived"}
                    </span>
                </div>

                {testable ? (
                    <form
                        className="tool-modal-test-form"
                        onSubmit={(event) => void runTest(event)}
                    >
                        <div className="tool-modal-section-heading">
                            <div>
                                <p className="panel-kicker">
                                    Safe execution preview
                                </p>
                                <h3>Test this tool</h3>
                            </div>
                            <FlaskConical size={17} aria-hidden="true" />
                        </div>
                        {httpTool ? (
                            <>
                                <label htmlFor="tool-modal-arguments">
                                    Request arguments (JSON)
                                    <textarea
                                        id="tool-modal-arguments"
                                        className="tool-modal-arguments"
                                        value={argumentsText}
                                        onChange={(event) => {
                                            setArgumentsText(
                                                event.target.value,
                                            );
                                            setArgumentsError(null);
                                            setError(null);
                                        }}
                                        onBlur={() =>
                                            setArgumentsText((value) =>
                                                value.trim() ? value : "{}\n",
                                            )
                                        }
                                        rows={7}
                                        spellCheck={false}
                                        aria-invalid={Boolean(argumentsError)}
                                        aria-describedby="tool-modal-arguments-help tool-modal-arguments-error"
                                        disabled={!versionDetail}
                                    />
                                    {argumentsError ? (
                                        <span
                                            id="tool-modal-arguments-error"
                                            className="create-tool-field-error"
                                        >
                                            {argumentsError}
                                        </span>
                                    ) : null}
                                    <span
                                        id="tool-modal-arguments-help"
                                        className="field-helper"
                                    >
                                        Edit the JSON object to match the input
                                        schema. Arguments are validated before
                                        the request is sent.
                                    </span>
                                </label>
                                <div className="tool-modal-test-options">
                                    <span className="tool-modal-request-label">
                                        {String(
                                            versionDetail?.executor.config
                                                .method ?? "GET",
                                        )}{" "}
                                        request
                                    </span>
                                    <button
                                        className="button primary-button"
                                        type="submit"
                                        disabled={testing || !versionDetail}
                                    >
                                        {testing ? (
                                            <>
                                                <LoaderCircle
                                                    className="spin"
                                                    size={15}
                                                    aria-hidden="true"
                                                />
                                                Sending…
                                            </>
                                        ) : (
                                            <>
                                                <ArrowUpRight
                                                    size={15}
                                                    aria-hidden="true"
                                                />
                                                Send test request
                                            </>
                                        )}
                                    </button>
                                </div>
                            </>
                        ) : (
                            <>
                                <label htmlFor="tool-modal-query">
                                    Sample query
                                </label>
                                <input
                                    id="tool-modal-query"
                                    value={query}
                                    onChange={(event) =>
                                        setQuery(event.target.value)
                                    }
                                    onBlur={() =>
                                        setQuery((value) => value.trim())
                                    }
                                    maxLength={2000}
                                />
                                <div className="tool-modal-test-options">
                                    <label htmlFor="tool-modal-results">
                                        Results
                                    </label>
                                    <select
                                        id="tool-modal-results"
                                        value={numResults}
                                        onChange={(event) =>
                                            setNumResults(event.target.value)
                                        }
                                    >
                                        <option value="5">5 results</option>
                                        <option value="10">10 results</option>
                                    </select>
                                    <button
                                        className="button primary-button"
                                        type="submit"
                                        disabled={testing || !query.trim()}
                                    >
                                        {testing ? (
                                            <>
                                                <LoaderCircle
                                                    className="spin"
                                                    size={15}
                                                    aria-hidden="true"
                                                />
                                                Searching…
                                            </>
                                        ) : (
                                            <>
                                                <Search
                                                    size={15}
                                                    aria-hidden="true"
                                                />
                                                Run search
                                            </>
                                        )}
                                    </button>
                                </div>
                                <p className="field-helper">
                                    Uses Exa Search with highlights. External
                                    pages are treated as untrusted data.
                                </p>
                            </>
                        )}
                    </form>
                ) : (
                    <div className="tool-inspect-note">
                        <ShieldCheck size={15} aria-hidden="true" />
                        <span>
                            This built-in tool is inspect-only in this preview.
                            Its immutable schemas are shown below.
                        </span>
                    </div>
                )}

                {error ? (
                    <div className="form-error tool-modal-alert" role="alert">
                        <AlertCircle size={15} aria-hidden="true" />
                        {error}
                    </div>
                ) : null}
                <div className="tool-schema-grid modal-schema-grid">
                    <SchemaBlock
                        title="Input schema"
                        schema={versionDetail?.input_schema}
                    />
                    <SchemaBlock
                        title="Output schema"
                        schema={versionDetail?.output_schema}
                    />
                </div>
                {testable ? (
                    <div className="tool-modal-result-area">
                        <div className="tool-modal-section-heading">
                            <div>
                                <p className="panel-kicker">
                                    {httpTool
                                        ? "HTTP response"
                                        : "Sanitized response"}
                                </p>
                                <h3>
                                    {httpTool
                                        ? "Test result"
                                        : "Search results"}
                                </h3>
                            </div>
                            {result?.status === "completed" ? (
                                <span className="tool-result-meta">
                                    <CheckCircle2
                                        size={14}
                                        aria-hidden="true"
                                    />
                                    Completed
                                </span>
                            ) : null}
                        </div>
                        <div
                            className="tool-modal-result-scroll"
                            aria-live="polite"
                        >
                            {testing ? (
                                <div className="tool-modal-result-state">
                                    <LoaderCircle
                                        className="spin"
                                        size={17}
                                        aria-hidden="true"
                                    />
                                    {httpTool
                                        ? "Sending HTTP request…"
                                        : "Searching the web…"}
                                </div>
                            ) : null}
                            {!testing && !result ? (
                                <div className="tool-modal-result-state">
                                    {httpTool
                                        ? "Send a test request to inspect the response."
                                        : "Run a sample query to inspect sanitized highlights."}
                                </div>
                            ) : null}
                            {!testing &&
                            result?.status === "completed" &&
                            httpTool ? (
                                <pre className="tool-http-result-output">
                                    {JSON.stringify(result.output, null, 2)}
                                </pre>
                            ) : null}
                            {!testing &&
                            result?.status === "completed" &&
                            !httpTool ? (
                                <div className="tool-results">
                                    {result.output?.results?.map((item) => (
                                        <article
                                            className="tool-result"
                                            key={item.url}
                                        >
                                            <strong>{item.title}</strong>
                                            <a
                                                href={item.url}
                                                target="_blank"
                                                rel="noreferrer"
                                            >
                                                {item.url}
                                            </a>
                                            {item.highlights.map(
                                                (highlight) => (
                                                    <p key={highlight}>
                                                        {highlight}
                                                    </p>
                                                ),
                                            )}
                                        </article>
                                    ))}
                                </div>
                            ) : null}
                            {!testing && result?.status === "failed" ? (
                                <div className="tool-modal-result-state error">
                                    <AlertCircle size={17} aria-hidden="true" />
                                    {result.error?.message ??
                                        "Tool execution failed."}
                                </div>
                            ) : null}
                        </div>
                    </div>
                ) : null}
            </section>
        </div>
    );
}

export default function ToolsPage() {
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [tools, setTools] = useState<Tool[]>([]);
    const [search, setSearch] = useState("");
    const [toolFilter, setToolFilter] = useState<ToolFilter>("ALL");
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(6);
    const [viewMode, setViewMode] = useState<ViewMode>("grid");
    const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
    const [selectedMcpGroup, setSelectedMcpGroup] =
        useState<MCPToolGroup | null>(null);
    const [versionDetail, setVersionDetail] =
        useState<ToolVersionDetail | null>(null);
    const [createOpen, setCreateOpen] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const savedView = window.localStorage.getItem("vf-tools-view");
        if (savedView === "grid" || savedView === "list")
            setViewMode(savedView);
        let cancelled = false;
        void apiFetch("/v1/workspaces")
            .then(async (response) => {
                if (!response.ok) throw new Error(await readApiError(response));
                const body = (await response.json()) as { data: Workspace[] };
                const saved = window.localStorage.getItem("vf-workspace-id");
                if (!cancelled)
                    setWorkspace(
                        body.data.find((item) => item.id === saved) ??
                            body.data[0] ??
                            null,
                    );
            })
            .catch((reason: unknown) => {
                if (!cancelled)
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : "Unable to load workspaces.",
                    );
            });
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        if (!workspace) {
            setLoading(false);
            return;
        }
        let cancelled = false;
        setLoading(true);
        void fetchTools(workspace.id)
            .then((items) => {
                if (!cancelled) setTools(items);
            })
            .catch((reason: unknown) => {
                if (!cancelled)
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : "Unable to load tools.",
                    );
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [workspace]);

    const filteredTools = useMemo(() => {
        const normalized = search.trim().toLowerCase();
        return tools.filter((tool) => {
            const matchesFilter =
                toolFilter === "ALL" ||
                (toolFilter === "BUILT_IN" && tool.built_in) ||
                (toolFilter === "HTTP" &&
                    !tool.built_in &&
                    tool.type === "HTTP") ||
                (toolFilter === "MCP" && tool.type === "MCP");
            const matchesSearch =
                !normalized ||
                [
                    tool.name,
                    tool.slug,
                    tool.description ?? "",
                    providerLabel(tool),
                    tool.type,
                    tool.mcp_server_name ?? "",
                ]
                    .join(" ")
                    .toLowerCase()
                    .includes(normalized);
            return matchesFilter && matchesSearch;
        });
    }, [search, toolFilter, tools]);

    const mcpGroups = useMemo<MCPToolGroup[]>(() => {
        const groups = new Map<string, MCPToolGroup>();
        for (const tool of filteredTools.filter(
            (item) => item.type === "MCP",
        )) {
            const groupId = tool.mcp_server_id ?? `tool:${tool.id}`;
            const existing = groups.get(groupId);
            if (existing) existing.tools.push(tool);
            else {
                groups.set(groupId, {
                    id: groupId,
                    name: tool.mcp_server_name ?? "MCP server",
                    tools: [tool],
                });
            }
        }
        return Array.from(groups.values()).sort((a, b) =>
            a.name.localeCompare(b.name),
        );
    }, [filteredTools]);

    useEffect(() => {
        setPage(1);
    }, [search, toolFilter]);

    const paginatedItemCount =
        toolFilter === "MCP" ? mcpGroups.length : filteredTools.length;
    const totalPages = Math.max(1, Math.ceil(paginatedItemCount / pageSize));
    const currentPage = Math.min(page, totalPages);
    const visibleMcpGroups = mcpGroups.slice(
        (currentPage - 1) * pageSize,
        currentPage * pageSize,
    );
    const visibleTools = filteredTools.slice(
        (currentPage - 1) * pageSize,
        currentPage * pageSize,
    );

    useEffect(() => {
        if (!selectedTool) {
            setVersionDetail(null);
            return;
        }
        const version = selectedTool.versions[0];
        if (!version) {
            setVersionDetail(null);
            return;
        }
        void fetchToolVersion(selectedTool.id, version.id)
            .then(setVersionDetail)
            .catch(() => setVersionDetail(null));
    }, [selectedTool]);

    function openTool(tool: Tool) {
        setError(null);
        setVersionDetail(null);
        setSelectedTool(tool);
    }

    function changeView(nextView: ViewMode) {
        setViewMode(nextView);
        window.localStorage.setItem("vf-tools-view", nextView);
    }

    async function handleDeleteTool(tool: Tool): Promise<void> {
        setError(null);
        try {
            await deleteTool(tool.id);
            setTools((current) =>
                current.filter((item) => item.id !== tool.id),
            );
            setSelectedTool((current) =>
                current?.id === tool.id ? null : current,
            );
            setSelectedMcpGroup(null);
        } catch (reason: unknown) {
            setError(
                reason instanceof Error
                    ? reason.message
                    : "Unable to delete tool.",
            );
        }
    }

    return (
        <AppShell>
            <div className="pagination-page">
                <div className="page-header tools-page-header">
                    <div>
                        <p className="eyebrow">VibesFactory / Build</p>
                        <h1>Tools</h1>
                        <p className="page-description">
                            Browse, inspect and test immutable capabilities
                            available to this workspace.
                        </p>
                    </div>
                    <div className="tools-header-actions">
                        <div className="tool-page-health">
                            <span className="status-pulse" aria-hidden="true" />
                            Catalog ready
                        </div>
                        <button
                            className="button primary-button"
                            type="button"
                            onClick={() => setCreateOpen(true)}
                        >
                            <Plus size={15} aria-hidden="true" />
                            New tool
                        </button>
                    </div>
                </div>

                {error ? (
                    <div className="form-error tool-alert" role="alert">
                        <AlertCircle size={16} aria-hidden="true" />
                        {error}
                    </div>
                ) : null}
                {!workspace && !loading ? (
                    <section className="panel tool-empty">
                        <Zap size={28} aria-hidden="true" />
                        <h2>Create a workspace first</h2>
                        <p className="panel-copy">
                            Built-in tools are scoped to a workspace.
                        </p>
                    </section>
                ) : null}
                {loading ? (
                    <section className="panel agent-state">
                        <LoaderCircle
                            className="spin"
                            size={18}
                            aria-hidden="true"
                        />
                        Loading tool catalog…
                    </section>
                ) : null}

                {workspace && !loading ? (
                    <>
                        <section
                            className="tools-toolbar"
                            aria-label="Tool catalog controls"
                        >
                            <label className="agent-search">
                                <Search size={16} aria-hidden="true" />
                                <span className="sr-only">Search tools</span>
                                <input
                                    value={search}
                                    onChange={(event) =>
                                        setSearch(event.target.value)
                                    }
                                    placeholder="Search tools…"
                                />
                            </label>
                            <div
                                className="tool-type-filters"
                                aria-label="Filter tools by type"
                            >
                                {(
                                    [
                                        ["ALL", "All", tools.length],
                                        [
                                            "BUILT_IN",
                                            "Built-in",
                                            tools.filter(
                                                (tool) => tool.built_in,
                                            ).length,
                                        ],
                                        [
                                            "HTTP",
                                            "HTTPS",
                                            tools.filter(
                                                (tool) =>
                                                    !tool.built_in &&
                                                    tool.type === "HTTP",
                                            ).length,
                                        ],
                                        [
                                            "MCP",
                                            "MCP",
                                            tools.filter(
                                                (tool) => tool.type === "MCP",
                                            ).length,
                                        ],
                                    ] as Array<[ToolFilter, string, number]>
                                ).map(([value, label, count]) => (
                                    <button
                                        className={
                                            toolFilter === value
                                                ? "selected"
                                                : ""
                                        }
                                        type="button"
                                        key={value}
                                        aria-pressed={toolFilter === value}
                                        onClick={() => setToolFilter(value)}
                                    >
                                        {label}
                                        <span>{count}</span>
                                    </button>
                                ))}
                            </div>
                            <div
                                className="layout-toggle"
                                aria-label="Tool layout"
                            >
                                <button
                                    type="button"
                                    className={
                                        viewMode === "grid" ? "selected" : ""
                                    }
                                    aria-label="Grid view"
                                    aria-pressed={viewMode === "grid"}
                                    onClick={() => changeView("grid")}
                                >
                                    <LayoutGrid size={15} aria-hidden="true" />
                                </button>
                                <button
                                    type="button"
                                    className={
                                        viewMode === "list" ? "selected" : ""
                                    }
                                    aria-label="List view"
                                    aria-pressed={viewMode === "list"}
                                    onClick={() => changeView("list")}
                                >
                                    <List size={15} aria-hidden="true" />
                                </button>
                            </div>
                        </section>
                        {filteredTools.length === 0 ? (
                            <section className="panel tool-empty">
                                <Search size={25} aria-hidden="true" />
                                <h2>No tools found</h2>
                                <p className="panel-copy">
                                    Try a different name, slug, provider or
                                    executor type.
                                </p>
                            </section>
                        ) : (
                            <section
                                className={
                                    "tools-card-grid " +
                                    (viewMode === "list" ? "list-view" : "")
                                }
                                aria-label={
                                    viewMode === "grid"
                                        ? "Tool cards"
                                        : "Tool list"
                                }
                            >
                                {toolFilter === "MCP"
                                    ? visibleMcpGroups.map((group) => (
                                          <MCPServerGroupCard
                                              key={group.id}
                                              group={group}
                                              onOpen={setSelectedMcpGroup}
                                          />
                                      ))
                                    : visibleTools.map((tool) => (
                                          <ToolCard
                                              key={tool.id}
                                              tool={tool}
                                              onOpen={openTool}
                                              onDelete={handleDeleteTool}
                                          />
                                      ))}
                            </section>
                        )}
                        <PaginationControls
                            page={currentPage}
                            pageSize={pageSize}
                            totalItems={paginatedItemCount}
                            onPageChange={setPage}
                            onPageSizeChange={setPageSize}
                            ariaLabel="Tools pagination"
                        />
                    </>
                ) : null}
                {selectedTool ? (
                    <ToolDetailModal
                        tool={selectedTool}
                        versionDetail={versionDetail}
                        onClose={() => setSelectedTool(null)}
                    />
                ) : null}
                {selectedMcpGroup ? (
                    <MCPToolsModal
                        group={selectedMcpGroup}
                        onClose={() => setSelectedMcpGroup(null)}
                        onInspect={(tool) => {
                            setSelectedMcpGroup(null);
                            openTool(tool);
                        }}
                        onDelete={handleDeleteTool}
                    />
                ) : null}
                {workspace && createOpen ? (
                    <CreateToolModal
                        workspaceId={workspace.id}
                        onClose={() => setCreateOpen(false)}
                        onCreated={async () => {
                            setCreateOpen(false);
                            setError(null);
                            setLoading(true);
                            try {
                                setTools(await fetchTools(workspace.id));
                            } catch (reason: unknown) {
                                setError(
                                    reason instanceof Error
                                        ? reason.message
                                        : "Unable to refresh the tool catalog.",
                                );
                            } finally {
                                setLoading(false);
                            }
                        }}
                    />
                ) : null}
            </div>
        </AppShell>
    );
}
