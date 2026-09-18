"use client";

import {
  AlertCircle,
  CheckCircle2,
  Check,
  CircleDashed,
  ChevronDown,
  ExternalLink,
  KeyRound,
  ListChecks,
  LoaderCircle,
  Network,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import {
  FormEvent,
  type KeyboardEvent,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import { AppShell } from "../../components/app-shell";
import { DeleteAction } from "../../components/delete-action";
import { PaginationControls } from "../../components/pagination-controls";
import { apiFetch, readApiError } from "../../lib/api";
import { fetchCredentials, type Credential } from "../../lib/credentials";
import {
  attachToolToDraft,
  createMCPServer,
  deleteMCPServer,
  discoverMCPServer,
  fetchMCPServers,
  fetchMCPTools,
  importMCPTool,
  testMCPServer,
  updateMCPServer,
  type MCPServer,
  type MCPTool,
} from "../../lib/mcp";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };
type Modal = "create" | "import" | null;
type PanelAction = "test" | "discover" | null;

type BulkImportEntry = {
  tool: MCPTool;
  name: string;
  slug: string;
};

type MCPHeaderDraft = { id: string; headerName: string; credentialId: string };

type MCPDropdownOption = { value: string; label: string; secondary?: string };

function MCPDropdown({
  label,
  value,
  options,
  placeholder,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  options: MCPDropdownOption[];
  placeholder: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const [highlightedIndex, setHighlightedIndex] = useState(
    Math.max(selectedIndex, 0),
  );
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : null;
  const displayLabel = label === "Authentication" ? "Authorization" : label;

  useEffect(() => {
    if (selectedIndex >= 0) setHighlightedIndex(selectedIndex);
  }, [selectedIndex]);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node))
        setOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled || options.length === 0) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const direction = event.key === "ArrowDown" ? 1 : -1;
      setHighlightedIndex(
        (index) => (index + direction + options.length) % options.length,
      );
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && !open) {
      event.preventDefault();
      setOpen(true);
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && open) {
      event.preventDefault();
      const option = options[highlightedIndex];
      if (option) {
        onChange(option.value);
        setOpen(false);
      }
      return;
    }
    if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
    }
  }

  return (
    <div className="mcp-dropdown-field">
      <span className="mcp-dropdown-label">{displayLabel}</span>
      <div className="mcp-dropdown" ref={rootRef}>
        <button
          className="mcp-dropdown-trigger"
          type="button"
          aria-label={displayLabel}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listboxId}
          disabled={disabled || options.length === 0}
          onClick={() => setOpen((current) => !current)}
          onKeyDown={handleKeyDown}
        >
          <span
            className={
              selectedOption ? "mcp-dropdown-value" : "mcp-dropdown-placeholder"
            }
          >
            {selectedOption?.label || placeholder}
          </span>
          <ChevronDown
            className={
              open ? "mcp-dropdown-chevron open" : "mcp-dropdown-chevron"
            }
            size={17}
            aria-hidden="true"
          />
        </button>
        {open ? (
          <div
            className="mcp-dropdown-menu"
            id={listboxId}
            role="listbox"
            aria-label={displayLabel}
          >
            {options.map((option, index) => (
              <button
                className={
                  index === highlightedIndex
                    ? "mcp-dropdown-option highlighted"
                    : "mcp-dropdown-option"
                }
                id={`${listboxId}-${index}`}
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                onMouseEnter={() => setHighlightedIndex(index)}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              >
                <span>
                  <strong>{option.label}</strong>
                  {option.secondary ? <small>{option.secondary}</small> : null}
                </span>
                {option.value === value ? (
                  <Check size={16} aria-hidden="true" />
                ) : null}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function statusCopy(server: MCPServer) {
  if (server.status === "DISABLED")
    return { label: "Disabled", className: "muted" };
  if (server.connection_status === "CONNECTED")
    return { label: "Connected", className: "success" };
  if (server.connection_status === "FAILED")
    return { label: "Needs attention", className: "warning" };
  return { label: "Not tested", className: "info" };
}

function toolStatus(tool: MCPTool) {
  return tool.status === "CHANGED"
    ? "Changed"
    : tool.status === "IMPORTED"
      ? "Imported"
      : tool.status === "REMOVED"
        ? "Removed"
        : "Available";
}

function slugifyToolName(value: string) {
  return (
    value
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "mcp-tool"
  );
}

function buildBulkImportEntries(selectedTools: MCPTool[]): BulkImportEntry[] {
  const used = new Map<string, number>();
  return selectedTools.map((tool) => {
    const name = tool.title?.trim() || tool.remote_name;
    const baseSlug = slugifyToolName(name);
    const count = used.get(baseSlug) ?? 0;
    used.set(baseSlug, count + 1);
    return {
      tool,
      name,
      slug: count === 0 ? baseSlug : `${baseSlug}-${count + 1}`,
    };
  });
}

function ToolImportSwitch({
  tool,
  checked,
  onChange,
}: {
  tool: MCPTool;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <button
      className={`mcp-switch ${checked ? "is-on" : ""}`}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={`${checked ? "Exclude" : "Include"} ${tool.title || tool.remote_name} in bulk import`}
      onClick={() => onChange(!checked)}
    >
      <span className="mcp-switch-track" aria-hidden="true">
        <span />
      </span>
    </button>
  );
}

export default function MCPServersPage() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [selectedServer, setSelectedServer] = useState<MCPServer | null>(null);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [selectedImportIds, setSelectedImportIds] = useState<Set<string>>(
    new Set(),
  );
  const [bulkImportEntries, setBulkImportEntries] = useState<BulkImportEntry[]>(
    [],
  );
  const [bulkProgress, setBulkProgress] = useState({ completed: 0, total: 0 });
  const [expandedDescriptions, setExpandedDescriptions] = useState<Set<string>>(
    new Set(),
  );
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState<Modal>(null);
  const [bulkImportOpen, setBulkImportOpen] = useState(false);
  const [selectedTool, setSelectedTool] = useState<MCPTool | null>(null);
  const [editingServer, setEditingServer] = useState<MCPServer | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmingServerId, setConfirmingServerId] = useState<string | null>(null);
  const [panelAction, setPanelAction] = useState<PanelAction>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const [form, setForm] = useState({
    name: "",
    endpoint: "",
    credentialId: "",
    authMode: "NONE" as "NONE" | "BEARER",
    headerName: "Authorization",
    prefix: "",
    customHeaders: [] as MCPHeaderDraft[],
  });
  const [importForm, setImportForm] = useState({
    name: "",
    slug: "",
    risk: "LOW" as "LOW" | "MEDIUM" | "HIGH",
    timeout: "30",
    sideEffect: false,
    idempotent: true,
  });
  const [agents, setAgents] = useState<Array<{ id: string; name: string }>>([]);
  const [attachAgent, setAttachAgent] = useState("");

  async function load() {
    setError("");
    try {
      const workspaceResponse = await apiFetch("/v1/workspaces");
      if (!workspaceResponse.ok)
        throw new Error(await readApiError(workspaceResponse));
      const workspaces = (
        (await workspaceResponse.json()) as { data: Workspace[] }
      ).data;
      const selected = workspaces[0] || null;
      setWorkspace(selected);
      if (!selected) return;
      const [nextServers, nextCredentials] = await Promise.all([
        fetchMCPServers(selected.id),
        fetchCredentials(selected.id),
      ]);
      setServers(nextServers);
      setCredentials(
        nextCredentials.filter((credential) => credential.status === "ACTIVE"),
      );
      const agentsResponse = await apiFetch(
        `/v1/workspaces/${selected.id}/agents`,
      );
      if (agentsResponse.ok) {
        setAgents(
          (
            (await agentsResponse.json()) as {
              data: Array<{ id: string; name: string }>;
            }
          ).data,
        );
      }
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load MCP servers.",
      );
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    setSelectedImportIds((current) => {
      const next = new Set<string>();
      for (const tool of tools) {
        if (
          current.has(tool.id) &&
          tool.available &&
          tool.status !== "IMPORTED"
        ) {
          next.add(tool.id);
        }
      }
      return next;
    });
  }, [tools]);

  useEffect(() => {
    if (!modal && !bulkImportOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const timer = window.setTimeout(
      () => dialogRef.current?.querySelector<HTMLElement>("input")?.focus(),
      0,
    );
    return () => {
      window.clearTimeout(timer);
      document.body.style.overflow = previous;
      triggerRef.current?.focus();
    };
  }, [bulkImportOpen, modal]);

  const filteredTools = useMemo(
    () =>
      tools.filter((tool) =>
        `${tool.remote_name} ${tool.description || ""}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [tools, search],
  );

  async function runServerAction(
    action: "test" | "discover",
    server: MCPServer,
    source: "panel" | "card" = "panel",
  ) {
    if (source === "panel") setPanelAction(action);
    else setBusy(`${action}:${server.id}`);
    setError("");
    setMessage("");
    try {
      if (action === "test") {
        const result = await testMCPServer(server.id);
        setMessage(
          result.status === "CONNECTED"
            ? `Connected in ${result.latency_ms}ms.`
            : result.error?.message || "The server could not be reached.",
        );
      } else {
        const result = await discoverMCPServer(server.id);
        setSelectedImportIds(new Set());
        setTools(result.tools);
        setSelectedServer({
          ...server,
          last_discovered_at: new Date().toISOString(),
        });
        setMessage(
          `Discovery complete: ${result.added} added, ${result.updated} updated, ${result.removed} removed.`,
        );
      }
      await load();
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : "The MCP action failed.",
      );
    } finally {
      if (source === "panel") setPanelAction(null);
      else setBusy(null);
    }
  }

  async function handleDeleteServer(server: MCPServer) {
    if (workspace?.role !== "OWNER") return;
    setBusy(`delete:${server.id}`);
    setError("");
    try {
      await deleteMCPServer(server.id);
      setServers((current) => current.filter((item) => item.id !== server.id));
      if (selectedServer?.id === server.id) setSelectedServer(null);
      setConfirmingServerId(null);
      setMessage(`${server.name} was deleted.`);
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : "Unable to delete MCP server.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function openServer(server: MCPServer) {
    setSelectedServer(server);
    setSelectedImportIds(new Set());
    setSearch("");
    setExpandedDescriptions(new Set());
    setMessage("");
    setError("");
    try {
      setTools(await fetchMCPTools(server.id));
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load discovered tools.",
      );
    }
  }

  async function submitServer(event: FormEvent) {
    event.preventDefault();
    setFormError("");
    setBusy("create");
    if (!workspace) return;
    if (
      form.customHeaders.some(
        (header) => !header.headerName.trim() || !header.credentialId,
      )
    ) {
      setFormError("Choose a Secret Store credential for every custom header.");
      setBusy(null);
      return;
    }
    if (form.authMode === "BEARER" && !form.credentialId) {
      setFormError("Select a credential for Authorization.");
      setBusy(null);
      return;
    }
    try {
      const input = {
        name: form.name.trim(),
        endpoint: form.endpoint.trim(),
        credential_id:
          form.authMode === "NONE" ? null : form.credentialId || null,
        auth: {
          mode: form.authMode,
          header_name: form.headerName,
          prefix: form.prefix,
          secret_key: "token",
          custom_headers: form.customHeaders.map((header) => ({
            header_name: header.headerName.trim(),
            credential_id: header.credentialId,
          })),
        },
      } as const;
      const server = editingServer
        ? await updateMCPServer(editingServer.id, input)
        : await createMCPServer(workspace.id, input);
      const result = await testMCPServer(server.id);
      await load();
      if (result.status === "FAILED") {
        setEditingServer(server);
        setSelectedServer(server);
        setFormError(
          result.error?.message || "The server could not be reached.",
        );
      } else {
        setModal(null);
        setEditingServer(null);
        setForm({
          name: "",
          endpoint: "",
          credentialId: "",
          authMode: "NONE",
          headerName: "Authorization",
          prefix: "",
          customHeaders: [],
        });
        setMessage(`Connected in ${result.latency_ms}ms.`);
      }
    } catch (submitError) {
      setFormError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to save the server.",
      );
    } finally {
      setBusy(null);
    }
  }

  function resetServerForm() {
    setForm({
      name: "",
      endpoint: "",
      credentialId: "",
      authMode: "NONE",
      headerName: "Authorization",
      prefix: "",
      customHeaders: [],
    });
  }

  function addCustomHeader() {
    const id =
      globalThis.crypto?.randomUUID?.() ||
      `mcp-header-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setForm((current) => ({
      ...current,
      customHeaders: [
        ...current.customHeaders,
        { id, headerName: "", credentialId: "" },
      ],
    }));
  }

  async function submitImport(event: FormEvent) {
    event.preventDefault();
    if (!selectedServer || !selectedTool) return;
    setBusy("import");
    setFormError("");
    try {
      const result = await importMCPTool(selectedServer.id, {
        remote_name: selectedTool.remote_name,
        tool_name: importForm.name.trim(),
        slug: importForm.slug.trim(),
        timeout_seconds: Number(importForm.timeout),
        risk_level: importForm.risk,
        side_effect: importForm.sideEffect,
        idempotent: importForm.idempotent,
      });
      setModal(null);
      setMessage(
        result.created
          ? `Imported as ToolVersion v${result.version_number}.`
          : "This schema is already imported.",
      );
      await openServer(selectedServer);
    } catch (submitError) {
      setFormError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to import the MCP tool.",
      );
    } finally {
      setBusy(null);
    }
  }

  function openBulkImport() {
    if (!selectedServer) return;
    const selectedTools = tools.filter(
      (tool) =>
        tool.available &&
        (selectedImportIds.size === 0 || selectedImportIds.has(tool.id)),
    );
    if (selectedTools.length === 0) return;
    triggerRef.current = document.activeElement as HTMLElement;
    setBulkImportEntries(buildBulkImportEntries(selectedTools));
    setBulkProgress({ completed: 0, total: selectedTools.length });
    setFormError("");
    setBulkImportOpen(true);
  }

  async function submitBulkImport(event: FormEvent) {
    event.preventDefault();
    if (!selectedServer || bulkImportEntries.length === 0) return;
    if (bulkImportEntries.some((entry) => !entry.name.trim())) {
      setFormError("Every selected tool needs a name before importing.");
      return;
    }
    setBusy("bulk-import");
    setFormError("");
    setBulkProgress({ completed: 0, total: bulkImportEntries.length });
    const failures: string[] = [];
    let imported = 0;
    for (const entry of bulkImportEntries) {
      try {
        await importMCPTool(selectedServer.id, {
          remote_name: entry.tool.remote_name,
          tool_name: entry.name.trim(),
          slug: entry.slug,
          timeout_seconds: 30,
          risk_level: "LOW",
          side_effect: false,
          idempotent: true,
        });
        imported += 1;
      } catch (importError) {
        failures.push(
          `${entry.name}: ${importError instanceof Error ? importError.message : "Import failed."}`,
        );
      } finally {
        setBulkProgress((current) => ({
          ...current,
          completed: current.completed + 1,
        }));
      }
    }
    await openServer(selectedServer);
    setBusy(null);
    if (failures.length > 0) {
      setFormError(
        `${imported} imported. ${failures.length} failed: ${failures[0]}`,
      );
      return;
    }
    setBulkImportOpen(false);
    setMessage(
      `${imported} MCP ${imported === 1 ? "tool" : "tools"} imported into the catalog.`,
    );
  }

  function updateBulkImportName(toolId: string, name: string) {
    setBulkImportEntries((current) => {
      const renamed = current.map((item) =>
        item.tool.id === toolId ? { ...item, name } : item,
      );
      const used = new Map<string, number>();
      return renamed.map((item) => {
        const baseSlug = slugifyToolName(item.name);
        const count = used.get(baseSlug) ?? 0;
        used.set(baseSlug, count + 1);
        return {
          ...item,
          slug: count === 0 ? baseSlug : `${baseSlug}-${count + 1}`,
        };
      });
    });
  }

  async function attachImportedTool(tool: MCPTool) {
    if (!tool.latest_imported_tool_version_id || !attachAgent) return;
    setBusy("attach");
    setError("");
    try {
      await attachToolToDraft(
        attachAgent,
        tool.latest_imported_tool_version_id,
      );
      setMessage(
        "Tool attached to the agent draft. Publish a new agent version to activate it.",
      );
    } catch (attachError) {
      setError(
        attachError instanceof Error
          ? attachError.message
          : "Unable to attach the tool.",
      );
    } finally {
      setBusy(null);
    }
  }

  function openImport(tool: MCPTool) {
    triggerRef.current = document.activeElement as HTMLElement;
    setSelectedTool(tool);
    setImportForm({
      name: tool.title || tool.remote_name,
      slug: tool.remote_name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, ""),
      risk: "LOW",
      timeout: "30",
      sideEffect: false,
      idempotent: true,
    });
    setModal("import");
  }

  const importableTools = tools.filter(
    (tool) => tool.available && tool.status !== "IMPORTED",
  );
  const selectedImportCount = importableTools.filter((tool) =>
    selectedImportIds.has(tool.id),
  ).length;
  const hasDiscoveredTools = tools.length > 0;

  const panelBusy = Boolean(panelAction);
  const totalPages = Math.max(1, Math.ceil(servers.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const visibleServers = servers.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );

  return (
    <AppShell>
      <div className="pagination-page mcp-page">
        <header className="page-header mcp-page-header">
          <div>
            <span className="panel-kicker">CONNECT / MCP</span>
            <h1>MCP Servers</h1>
            <p>
              Connect trusted Model Context Protocol servers and promote their
              tools into immutable agent capabilities.
            </p>
          </div>
          <button
            className="button primary-button"
            type="button"
            onClick={() => {
              triggerRef.current = document.activeElement as HTMLElement;
              setEditingServer(null);
              resetServerForm();
              setModal("create");
            }}
          >
            <Plus size={16} aria-hidden="true" /> Add MCP server
          </button>
        </header>

        {message ? (
          <div
            className="mcp-feedback success"
            role="status"
            aria-atomic="true"
          >
            <CheckCircle2 size={16} aria-hidden="true" /> {message}
          </div>
        ) : null}
        {error ? (
          <div className="mcp-feedback error" role="alert">
            <AlertCircle size={16} aria-hidden="true" /> {error}
          </div>
        ) : null}

        <section className="mcp-server-grid" aria-label="MCP servers">
          {servers.length === 0 ? (
            <div className="mcp-empty-state">
              <div className="mcp-empty-icon">
                <Network size={28} aria-hidden="true" />
              </div>
              <span className="panel-kicker">GET STARTED</span>
              <h2>No MCP servers yet</h2>
              <p>
                Connect your first Streamable HTTP server to discover tools and
                make them available to your agents.
              </p>
              <button
                className="button primary-button"
                type="button"
                onClick={() => {
                  setEditingServer(null);
                  setModal("create");
                }}
              >
                <Plus size={15} aria-hidden="true" /> Create your first MCP
                server
              </button>
              <small>Streamable HTTP · Credential Vault supported</small>
            </div>
          ) : (
            visibleServers.map((server) => {
              const state = statusCopy(server);
              const cardTesting = busy === `test:${server.id}`;
              return (
                <article className="mcp-server-card" key={server.id}>
                  <button
                    className="mcp-server-card-main"
                    type="button"
                    onClick={() => void openServer(server)}
                  >
                    <div className="mcp-card-icon">
                      <Network size={20} aria-hidden="true" />
                    </div>
                    <div className="mcp-card-copy">
                      <div className="mcp-card-title">
                        <h2>{server.name}</h2>
                        <span className={`status-badge ${state.className}`}>
                          <span />
                          {state.label}
                        </span>
                      </div>
                      <p>{server.endpoint}</p>
                      <div className="mcp-card-meta">
                        <span>
                          <small>Transport</small>
                          <b>Streamable HTTP</b>
                        </span>
                        <span>
                          <small>Tools</small>
                          <b>{server.tool_count}</b>
                        </span>
                        <span>
                          <small>Credential</small>
                          <b>
                            {server.credential_id ? (
                              <>
                                <KeyRound size={12} aria-hidden="true" />{" "}
                                Configured
                              </>
                            ) : (
                              "None"
                            )}
                          </b>
                        </span>
                      </div>
                    </div>
                    <ExternalLink size={16} aria-hidden="true" />
                  </button>
                  <footer>
                    <span>
                      {server.last_discovered_at
                        ? `Discovered ${new Date(server.last_discovered_at).toLocaleString()}`
                        : "Discovery not run"}
                    </span>
                    <div className="card-footer-actions">
                      <button
                        className="icon-button"
                        type="button"
                        aria-label={`Test ${server.name}`}
                        disabled={cardTesting || panelBusy || busy === `delete:${server.id}`}
                        onClick={() =>
                          void runServerAction("test", server, "card")
                        }
                      >
                        {cardTesting ? (
                          <LoaderCircle
                            className="spin"
                            size={16}
                            aria-hidden="true"
                          />
                        ) : (
                          <RefreshCw size={16} aria-hidden="true" />
                        )}
                      </button>
                      {workspace?.role === "OWNER" ? (
                        <DeleteAction
                          label={server.name}
                          confirming={confirmingServerId === server.id}
                          busy={busy === `delete:${server.id}`}
                          onRequest={() => setConfirmingServerId(server.id)}
                          onCancel={() => setConfirmingServerId(null)}
                          onConfirm={() => void handleDeleteServer(server)}
                        />
                      ) : null}
                    </div>
                  </footer>
                </article>
              );
            })
          )}
        </section>
        <PaginationControls page={currentPage} pageSize={pageSize} totalItems={servers.length} onPageChange={setPage} onPageSizeChange={setPageSize} ariaLabel="MCP servers pagination" />

        {selectedServer ? (
          <aside
            className="mcp-detail-panel"
            aria-label={`${selectedServer.name} details`}
          >
            <div className="mcp-detail-header">
              <div>
                <span className="panel-kicker">SERVER DETAIL</span>
                <h2>{selectedServer.name}</h2>
              </div>
              <button
                className="icon-button"
                type="button"
                aria-label="Close server details"
                onClick={() => setSelectedServer(null)}
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <div className="mcp-detail-actions">
              <button
                className="button secondary-button"
                type="button"
                disabled={Boolean(busy) || panelBusy}
                onClick={() => void runServerAction("test", selectedServer)}
              >
                {panelAction === "test" ? (
                  <LoaderCircle className="spin" size={15} aria-hidden="true" />
                ) : (
                  <RefreshCw size={15} aria-hidden="true" />
                )}{" "}
                {panelAction === "test"
                  ? "Testing connection..."
                  : "Test connection"}
              </button>
              <button
                className="button primary-button"
                type="button"
                disabled={Boolean(busy) || panelBusy}
                onClick={() => void runServerAction("discover", selectedServer)}
              >
                {panelAction === "discover" ? (
                  <LoaderCircle className="spin" size={15} aria-hidden="true" />
                ) : (
                  <Search size={15} aria-hidden="true" />
                )}{" "}
                {panelAction === "discover"
                  ? "Discovering tools..."
                  : "Discover tools"}
              </button>
            </div>
            {panelAction === "test" ? (
              <div
                className="mcp-panel-progress"
                role="status"
                aria-live="polite"
              >
                <LoaderCircle className="spin" size={15} aria-hidden="true" />
                <span>Testing connection...</span>
              </div>
            ) : null}
            {panelAction === "discover" ? (
              <div
                className="mcp-panel-progress"
                role="status"
                aria-live="polite"
              >
                <LoaderCircle className="spin" size={15} aria-hidden="true" />
                <span>Discovering tools...</span>
              </div>
            ) : null}
            {hasDiscoveredTools ? (
              <div className="mcp-tool-toolbar">
                <label htmlFor="mcp-tool-search">
                  Filter tools
                  <input
                    id="mcp-tool-search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search remote tools"
                  />
                </label>
                <div className="mcp-bulk-import-bar">
                  <span>
                    {selectedImportCount > 0 ? (
                      <>
                        <strong>{selectedImportCount}</strong> of{" "}
                        {importableTools.length} available tools selected
                      </>
                    ) : (
                      <>
                        <strong>{importableTools.length}</strong> available
                        tools · Import all includes every tool
                      </>
                    )}
                  </span>
                  <button
                    className="button primary-button"
                    type="button"
                    disabled={
                      !importableTools.length || Boolean(busy) || panelBusy
                    }
                    onClick={openBulkImport}
                  >
                    <ListChecks size={15} aria-hidden="true" /> Import all
                  </button>
                </div>
              </div>
            ) : null}
            <div className="mcp-tool-list">
              {panelAction === "discover" ? (
                <div
                  className="mcp-tools-loading"
                  role="status"
                  aria-label="Tools are loading"
                >
                  <div className="mcp-tools-loading-copy">
                    <LoaderCircle
                      className="spin"
                      size={18}
                      aria-hidden="true"
                    />
                    <span>Loading tools</span>
                  </div>
                  <div className="mcp-skeleton-list" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              ) : filteredTools.length === 0 ? (
                <div className="mcp-tool-empty">
                  <CircleDashed size={20} aria-hidden="true" /> Run discovery to
                  load tools.
                </div>
              ) : (
                filteredTools.map((tool) => {
                  const fullDescription =
                    tool.description?.trim() ||
                    "No description provided by the server.";
                  const isLongDescription = fullDescription.length > 100;
                  const isExpanded = expandedDescriptions.has(tool.id);
                  const visibleDescription =
                    isExpanded || !isLongDescription
                      ? fullDescription
                      : `${fullDescription.slice(0, 100).trimEnd()}...`;
                  return (
                    <div className="mcp-tool-row" key={tool.id}>
                      <div className="mcp-tool-row-copy">
                        <div className="mcp-tool-title">
                          <strong>{tool.title || tool.remote_name}</strong>
                          <span
                            className={`mcp-tool-state ${tool.status.toLowerCase()}`}
                          >
                            {toolStatus(tool)}
                          </span>
                        </div>
                        <code>{tool.remote_name}</code>
                        <p
                          className={
                            isExpanded
                              ? "mcp-tool-description expanded"
                              : "mcp-tool-description"
                          }
                        >
                          {visibleDescription}
                        </p>
                        {isLongDescription ? (
                          <button
                            className="mcp-see-more"
                            type="button"
                            aria-expanded={isExpanded}
                            onClick={() =>
                              setExpandedDescriptions((current) => {
                                const next = new Set(current);
                                if (isExpanded) next.delete(tool.id);
                                else next.add(tool.id);
                                return next;
                              })
                            }
                          >
                            {isExpanded ? "See less" : "See more"}
                          </button>
                        ) : null}
                      </div>
                      <div className="mcp-tool-actions">
                        {tool.available && tool.status !== "IMPORTED" ? (
                          <ToolImportSwitch
                            tool={tool}
                            checked={selectedImportIds.has(tool.id)}
                            onChange={(checked) =>
                              setSelectedImportIds((current) => {
                                const next = new Set(current);
                                if (checked) next.add(tool.id);
                                else next.delete(tool.id);
                                return next;
                              })
                            }
                          />
                        ) : null}
                        <button
                          className="button tertiary-button"
                          type="button"
                          disabled={
                            !tool.available || Boolean(busy) || panelBusy
                          }
                          onClick={() => openImport(tool)}
                        >
                          {tool.status === "IMPORTED" ? "Re-import" : "Import"}
                        </button>
                        {tool.latest_imported_tool_version_id &&
                        agents.length ? (
                          <>
                            <select
                              className="primary-select"
                              aria-label={`Choose an agent for ${tool.remote_name}`}
                              value={attachAgent}
                              onChange={(event) =>
                                setAttachAgent(event.target.value)
                              }
                            >
                              <option value="">Attach to…</option>
                              {agents.map((agent) => (
                                <option key={agent.id} value={agent.id}>
                                  {agent.name}
                                </option>
                              ))}
                            </select>
                            <button
                              className="button tertiary-button"
                              type="button"
                              disabled={
                                !attachAgent || Boolean(busy) || panelBusy
                              }
                              onClick={() => {
                                setSelectedTool(tool);
                                void attachImportedTool(tool);
                              }}
                            >
                              Attach
                            </button>
                          </>
                        ) : null}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </aside>
        ) : null}

        {modal ? (
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !busy) setModal(null);
            }}
          >
            <div
              className="modal-dialog mcp-modal"
              ref={dialogRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby="mcp-modal-title"
            >
              <button
                className="icon-button modal-close"
                type="button"
                aria-label="Close dialog"
                onClick={() => !busy && setModal(null)}
              >
                <X size={18} aria-hidden="true" />
              </button>
              {modal === "create" ? (
                <form onSubmit={submitServer}>
                  <span className="panel-kicker">NEW CONNECTION</span>
                  <h2 id="mcp-modal-title">Add MCP server</h2>
                  <p className="field-helper">
                    Use a Streamable HTTP endpoint. Secrets stay in the
                    credential vault.
                  </p>
                  <label>
                    Name
                    <input
                      required
                      value={form.name}
                      onChange={(event) =>
                        setForm({ ...form, name: event.target.value })
                      }
                      placeholder="GitHub MCP"
                    />
                  </label>
                  <label>
                    Endpoint
                    <input
                      required
                      type="url"
                      value={form.endpoint}
                      onChange={(event) =>
                        setForm({ ...form, endpoint: event.target.value })
                      }
                      placeholder="https://mcp.example.com/mcp"
                    />
                  </label>
                  <MCPDropdown
                    label="Authentication"
                    value={form.authMode}
                    options={[
                      { value: "NONE", label: "No Authorization" },
                      { value: "BEARER", label: "Bearer token" },
                    ]}
                    placeholder="Select authentication"
                    onChange={(value) =>
                      setForm({
                        ...form,
                        authMode: value as typeof form.authMode,
                      })
                    }
                  />
                  {form.authMode === "BEARER" ? (
                    <>
                      <MCPDropdown
                        label="Credential"
                        value={form.credentialId}
                        options={credentials.map((credential) => ({
                          value: credential.id,
                          label: credential.name,
                          secondary: credential.provider,
                        }))}
                        placeholder="Select a credential"
                        onChange={(value) =>
                          setForm({ ...form, credentialId: value })
                        }
                      />
                      <label>
                        Prefix <span className="field-optional">optional</span>
                        <input
                          value={form.prefix}
                          onChange={(event) =>
                            setForm({ ...form, prefix: event.target.value })
                          }
                          placeholder="Bearer"
                        />
                      </label>
                    </>
                  ) : null}
                  <section
                    className="mcp-custom-headers"
                    aria-labelledby="custom-headers-title"
                  >
                    <div className="mcp-custom-headers-heading">
                      <div>
                        <strong id="custom-headers-title">
                          Custom headers{" "}
                          <span className="field-optional">optional</span>
                        </strong>
                        <p>
                          Choose a Secret Store credential for each header
                          value. Custom headers can be used with or without
                          Authorization.
                        </p>
                      </div>
                      <button
                        className="button secondary-button mcp-add-header"
                        type="button"
                        onClick={addCustomHeader}
                      >
                        <Plus size={14} aria-hidden="true" /> Add custom header
                      </button>
                    </div>
                    {form.customHeaders.length === 0 ? (
                      <p className="mcp-custom-headers-empty">
                        Add a header name and choose the Secret Store entry that
                        supplies its value, for example <code>x-instance</code>{" "}
                        → <code>service-now-instance</code>.
                      </p>
                    ) : (
                      <div className="mcp-custom-header-list">
                        {form.customHeaders.map((header, index) => (
                          <div
                            className="mcp-custom-header-row"
                            key={header.id}
                          >
                            <label htmlFor={`mcp-header-name-${index}`}>
                              Header name
                              <input
                                id={`mcp-header-name-${index}`}
                                required
                                value={header.headerName}
                                onChange={(event) =>
                                  setForm((current) => ({
                                    ...current,
                                    customHeaders: current.customHeaders.map(
                                      (item, itemIndex) =>
                                        itemIndex === index
                                          ? {
                                              ...item,
                                              headerName: event.target.value,
                                            }
                                          : item,
                                    ),
                                  }))
                                }
                                placeholder="x-instance"
                              />
                            </label>
                            <MCPDropdown
                              label="Secret Store credential"
                              value={header.credentialId}
                              options={credentials.map((credential) => ({
                                value: credential.id,
                                label: credential.name,
                                secondary: credential.provider,
                              }))}
                              placeholder={
                                credentials.length
                                  ? "Select a Secret Store credential"
                                  : "No credentials available"
                              }
                              disabled={credentials.length === 0}
                              onChange={(value) =>
                                setForm((current) => ({
                                  ...current,
                                  customHeaders: current.customHeaders.map(
                                    (item, itemIndex) =>
                                      itemIndex === index
                                        ? { ...item, credentialId: value }
                                        : item,
                                  ),
                                }))
                              }
                            />
                            <button
                              className="icon-button mcp-remove-header"
                              type="button"
                              aria-label={`Remove custom header ${index + 1}`}
                              onClick={() =>
                                setForm((current) => ({
                                  ...current,
                                  customHeaders: current.customHeaders.filter(
                                    (_, itemIndex) => itemIndex !== index,
                                  ),
                                }))
                              }
                            >
                              <Trash2 size={15} aria-hidden="true" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                  {formError ? (
                    <div className="form-error" role="alert">
                      <AlertCircle size={15} aria-hidden="true" />
                      {formError}
                    </div>
                  ) : null}
                  <footer className="modal-actions">
                    <button
                      className="button secondary-button"
                      type="button"
                      disabled={Boolean(busy)}
                      onClick={() => setModal(null)}
                    >
                      Cancel
                    </button>
                    <button
                      className="button primary-button"
                      disabled={busy === "create"}
                      type="submit"
                    >
                      {busy === "create" ? (
                        <LoaderCircle
                          className="spin"
                          size={15}
                          aria-hidden="true"
                        />
                      ) : (
                        <ShieldAlert size={15} aria-hidden="true" />
                      )}{" "}
                      Save &amp; test
                    </button>
                  </footer>
                </form>
              ) : (
                <form onSubmit={submitImport}>
                  <span className="panel-kicker">IMPORT SNAPSHOT</span>
                  <h2 id="mcp-modal-title">
                    Import {selectedTool?.title || selectedTool?.remote_name}
                  </h2>
                  <p className="field-helper">
                    This creates an immutable ToolVersion. Re-import after
                    schema drift to create a new version.
                  </p>
                  <label>
                    Tool name
                    <input
                      required
                      value={importForm.name}
                      onChange={(event) =>
                        setImportForm({
                          ...importForm,
                          name: event.target.value,
                        })
                      }
                    />
                  </label>
                  <label>
                    Slug
                    <input
                      required
                      pattern="[a-z0-9][a-z0-9_-]*"
                      value={importForm.slug}
                      onChange={(event) =>
                        setImportForm({
                          ...importForm,
                          slug: event.target.value,
                        })
                      }
                    />
                  </label>
                  <div className="mcp-form-grid">
                    <MCPDropdown
                      label="Risk"
                      value={importForm.risk}
                      options={[
                        { value: "LOW", label: "Low" },
                        { value: "MEDIUM", label: "Medium" },
                        { value: "HIGH", label: "High" },
                      ]}
                      placeholder="Select risk"
                      onChange={(value) =>
                        setImportForm({
                          ...importForm,
                          risk: value as typeof importForm.risk,
                        })
                      }
                    />
                    <label>
                      Timeout (s)
                      <input
                        type="number"
                        min="1"
                        max="3600"
                        value={importForm.timeout}
                        onChange={(event) =>
                          setImportForm({
                            ...importForm,
                            timeout: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={importForm.sideEffect}
                      onChange={(event) =>
                        setImportForm({
                          ...importForm,
                          sideEffect: event.target.checked,
                        })
                      }
                    />{" "}
                    This tool has side effects
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={importForm.idempotent}
                      onChange={(event) =>
                        setImportForm({
                          ...importForm,
                          idempotent: event.target.checked,
                        })
                      }
                    />{" "}
                    Safe to retry
                  </label>
                  {formError ? (
                    <div className="form-error" role="alert">
                      <AlertCircle size={15} aria-hidden="true" />
                      {formError}
                    </div>
                  ) : null}
                  <footer className="modal-actions">
                    <button
                      className="button secondary-button"
                      type="button"
                      disabled={Boolean(busy)}
                      onClick={() => setModal(null)}
                    >
                      Cancel
                    </button>
                    <button
                      className="button primary-button"
                      disabled={busy === "import"}
                      type="submit"
                    >
                      {busy === "import" ? (
                        <LoaderCircle
                          className="spin"
                          size={15}
                          aria-hidden="true"
                        />
                      ) : (
                        <Network size={15} aria-hidden="true" />
                      )}{" "}
                      Import snapshot
                    </button>
                  </footer>
                </form>
              )}
            </div>
          </div>
        ) : null}
        {bulkImportOpen ? (
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !busy)
                setBulkImportOpen(false);
            }}
          >
            <div
              className="modal-dialog mcp-modal mcp-bulk-import-modal"
              ref={dialogRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby="bulk-import-title"
            >
              <button
                className="icon-button modal-close"
                type="button"
                aria-label="Close import preview"
                onClick={() => !busy && setBulkImportOpen(false)}
              >
                <X size={18} aria-hidden="true" />
              </button>
              <form onSubmit={submitBulkImport}>
                <span className="panel-kicker">REVIEW BULK IMPORT</span>
                <h2 id="bulk-import-title">
                  Import {bulkImportEntries.length} MCP tools
                </h2>
                <p className="field-helper">
                  Review the display name for every tool before creating
                  immutable ToolVersions. Slugs are generated automatically from
                  each name.
                </p>
                <div className="bulk-import-summary">
                  <ListChecks size={16} aria-hidden="true" />
                  <span>
                    <strong>
                      {bulkProgress.completed}/{bulkProgress.total}
                    </strong>{" "}
                    imported
                  </span>
                  <span className="bulk-import-summary-muted">
                    Defaults: LOW risk · 30s timeout · idempotent
                  </span>
                </div>
                <div className="bulk-import-list">
                  {bulkImportEntries.map((entry, index) => (
                    <div className="bulk-import-item" key={entry.tool.id}>
                      <div className="bulk-import-item-heading">
                        <span className="bulk-import-index">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <div>
                          <strong>{entry.tool.remote_name}</strong>
                          <small>
                            {entry.tool.description?.trim() ||
                              "No description provided by the server."}
                          </small>
                        </div>
                      </div>
                      <label htmlFor={`bulk-tool-name-${entry.tool.id}`}>
                        Tool name
                        <input
                          id={`bulk-tool-name-${entry.tool.id}`}
                          required
                          value={entry.name}
                          onChange={(event) =>
                            updateBulkImportName(
                              entry.tool.id,
                              event.target.value,
                            )
                          }
                        />
                      </label>
                      <div className="bulk-import-slug">
                        <span>Generated slug</span>
                        <code>{entry.slug || "mcp-tool"}</code>
                      </div>
                    </div>
                  ))}
                </div>
                {formError ? (
                  <div className="form-error" role="alert">
                    <AlertCircle size={15} aria-hidden="true" />
                    {formError}
                  </div>
                ) : null}
                <footer className="modal-actions">
                  <button
                    className="button secondary-button"
                    type="button"
                    disabled={Boolean(busy)}
                    onClick={() => setBulkImportOpen(false)}
                  >
                    Cancel
                  </button>
                  <button
                    className="button primary-button"
                    disabled={
                      busy === "bulk-import" || !bulkImportEntries.length
                    }
                    type="submit"
                  >
                    {busy === "bulk-import" ? (
                      <>
                        <LoaderCircle
                          className="spin"
                          size={15}
                          aria-hidden="true"
                        />{" "}
                        Importing {bulkProgress.completed}/{bulkProgress.total}
                        ...
                      </>
                    ) : (
                      <>
                        <ListChecks size={15} aria-hidden="true" /> Import all{" "}
                        {bulkImportEntries.length}
                      </>
                    )}
                  </button>
                </footer>
              </form>
            </div>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
