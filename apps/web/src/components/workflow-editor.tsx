"use client";

import { addEdge, Background, Controls, MiniMap, ReactFlow, ReactFlowProvider, Handle, Position, applyEdgeChanges, applyNodeChanges, type Connection, type Edge, type Node, type NodeProps, type OnEdgesChange, type OnNodesChange, type ReactFlowInstance } from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { Braces, Check, ChevronDown, CircleAlert, Database, GitBranch, Info, LayoutGrid, LoaderCircle, PanelRightClose, PanelRightOpen, Play, Plus, Save, Search, Settings2, ShieldCheck, Sparkles, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import type { Agent, AgentVersionSummary } from "../lib/agents";
import { ApiRequestError } from "../lib/api";
import type { Tool } from "../lib/tools";
import { FeedbackToast, type FeedbackToastState } from "./feedback-toast";
import { publishWorkflow, runWorkflow, saveWorkflowDraft, validateWorkflowDraft, type WorkflowDefinition, type WorkflowDraft, type WorkflowNode as DefinitionNode } from "../lib/workflows";

type CanvasNodeData = { label: string; type: DefinitionNode["type"]; config: Record<string, unknown> };
type CanvasNode = Node<CanvasNodeData>;

const colors: Record<DefinitionNode["type"], string> = { START: "var(--success)", END: "var(--error)", AGENT: "var(--brand-primary)", TOOL: "var(--info)", CONDITION: "var(--warning)", TRANSFORM: "var(--focus-ring)", APPROVAL: "var(--brand-primary)" };
const typeLabels: Record<DefinitionNode["type"], string> = { START: "Start", END: "End", AGENT: "Agent", TOOL: "Tool", CONDITION: "Condition", TRANSFORM: "Transform", APPROVAL: "Approval" };

function WorkflowNode({ data, selected }: NodeProps<CanvasNode>) {
  return <div className={`workflow-canvas-node ${selected ? "selected" : ""}`} style={{ "--node-accent": colors[data.type] } as React.CSSProperties} tabIndex={0} aria-label={`${typeLabels[data.type]} node: ${data.label}`}>
    {data.type !== "START" ? <Handle type="target" position={Position.Left} /> : null}
    <div className="workflow-node-icon"><GitBranch size={14} aria-hidden="true" /></div><div className="workflow-node-copy"><strong>{data.label}</strong><small>{data.type}</small></div>
    {data.type === "CONDITION" ? <><Handle id="true" type="source" position={Position.Right} style={{ top: "35%" }} /><Handle id="false" type="source" position={Position.Right} style={{ top: "70%" }} /></> : data.type === "APPROVAL" ? <><Handle id="approved" type="source" position={Position.Right} style={{ top: "35%" }} /><Handle id="rejected" type="source" position={Position.Right} style={{ top: "70%" }} /></> : data.type !== "END" ? <Handle type="source" position={Position.Right} /> : null}
  </div>;
}

const nodeTypes = { workflow: WorkflowNode };

function toCanvas(definition: WorkflowDefinition): { nodes: CanvasNode[]; edges: Edge[] } {
  return { nodes: definition.nodes.map((node) => ({ id: node.key, type: "workflow", position: node.position ?? { x: 80, y: 100 }, data: { label: node.name, type: node.type, config: node.config } })), edges: definition.edges.map((edge, index) => ({ id: `edge-${index}-${edge.source}-${edge.target}`, source: edge.source, target: edge.target, sourceHandle: edge.source_handle ?? undefined, type: "smoothstep", animated: false })) };
}

function toDefinition(nodes: CanvasNode[], edges: Edge[], base: WorkflowDefinition): WorkflowDefinition {
  return { ...base, nodes: nodes.map((node) => ({ key: node.id, type: node.data.type, name: node.data.label, config: normalizeNodeConfig(node.data.type, node.data.config), position: node.position })), edges: edges.map((edge) => ({ source: edge.source, target: edge.target, source_handle: edge.sourceHandle ?? null })) };
}

function autoLayout(nodes: CanvasNode[], edges: Edge[]) {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 70, ranksep: 110 });
  nodes.forEach((node) => graph.setNode(node.id, { width: 190, height: 64 }));
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);
  return nodes.map((node) => { const point = graph.node(node.id); return { ...node, position: { x: point.x - 95, y: point.y - 32 } }; });
}

type RefScope = "input" | "variables" | "node";
type RefExpression = { kind: "ref"; scope: RefScope; path: string; node_key?: string };
type LiteralExpression = { kind: "literal"; value: unknown };
type ExpressionValue = RefExpression | LiteralExpression;

type RunInputField = {
  id: string;
  key: string;
  value: string;
  type: "text" | "number" | "boolean";
};

function readRef(value: unknown, fallback: RefExpression): RefExpression {
  if (!value || typeof value !== "object") return fallback;
  const candidate = value as Partial<RefExpression>;
  if (candidate.kind !== "ref" || !candidate.scope || typeof candidate.path !== "string") return fallback;
  return { kind: "ref", scope: candidate.scope, path: candidate.path, ...(candidate.scope === "node" && candidate.node_key ? { node_key: candidate.node_key } : {}) };
}

function readExpression(value: unknown, fallback: ExpressionValue): ExpressionValue {
  if (!value || typeof value !== "object") return fallback;
  const candidate = value as Partial<ExpressionValue>;
  if (candidate.kind === "literal") return { kind: "literal", value: candidate.value ?? "" };
  if (candidate.kind === "ref" && candidate.scope && typeof candidate.path === "string") {
    return { kind: "ref", scope: candidate.scope, path: candidate.path, ...(candidate.scope === "node" && candidate.node_key ? { node_key: candidate.node_key } : {}) };
  }
  return fallback;
}

function displayPath(path: string) {
  return path.replace(/^\//, "").replaceAll("~1", "/").replaceAll("~0", "~");
}

function humanizePath(path: string) {
  const parts = displayPath(path)
    .split("/")
    .filter(Boolean)
    .map((part) => part.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()));
  return parts.length > 0 ? parts.join(" → ") : "Complete value";
}

function editablePath(path: string) {
  if (!path) return "";
  return displayPath(path).split("/").join(" → ");
}

function toFriendlyPath(value: string) {
  const segments = value.includes("→")
    ? value.split("→")
    : value.includes("/")
      ? value.split("/")
      : [value];
  const normalized = segments
    .map((segment) => segment.trim())
    .filter(Boolean)
    .join("/");
  return toPointer(normalized);
}

function toPointer(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("/")) return trimmed;
  return `/${trimmed.split("/").map((part) => part.replaceAll("~", "~0").replaceAll("/", "~1")).join("/")}`;
}

function normalizeNodeConfig(type: DefinitionNode["type"], config: Record<string, unknown>) {
  const normalizedConfig = normalizeExpressionPaths(config) as Record<string, unknown>;
  if (type !== "TOOL" && type !== "TRANSFORM") return normalizedConfig;
  const field = type === "TOOL" ? "arguments" : "assignments";
  const assignments = normalizedConfig[field];
  if (!Array.isArray(assignments)) return normalizedConfig;
  return {
    ...normalizedConfig,
    [field]: assignments.map((assignment) => {
      if (!assignment || typeof assignment !== "object") return assignment;
      const item = assignment as Record<string, unknown>;
      return { ...item, target: typeof item.target === "string" ? toPointer(item.target) : item.target };
    }),
  };
}

function normalizeExpressionPaths(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => normalizeExpressionPaths(item));
  if (!value || typeof value !== "object") return value;
  const record = value as Record<string, unknown>;
  const normalized = Object.fromEntries(Object.entries(record).map(([key, item]) => [key, normalizeExpressionPaths(item)]));
  if (normalized.kind === "ref" && typeof normalized.path === "string") normalized.path = toPointer(normalized.path);
  return normalized;
}

function resetDeletedNodeReferences(value: unknown, deletedNodeKeys: Set<string>): unknown {
  if (Array.isArray(value)) return value.map((item) => resetDeletedNodeReferences(item, deletedNodeKeys));
  if (!value || typeof value !== "object") return value;
  const record = value as Record<string, unknown>;
  if (record.kind === "ref" && record.scope === "node" && typeof record.node_key === "string" && deletedNodeKeys.has(record.node_key)) {
    return { kind: "ref", scope: "input", path: "" };
  }
  return Object.fromEntries(Object.entries(record).map(([key, item]) => [key, resetDeletedNodeReferences(item, deletedNodeKeys)]));
}

type WorkflowSelectOption = { value: string; label: string; secondary?: string };

/** The workflow form uses the same themed, keyboard-friendly select language as the rest of the console. */
function WorkflowSelect({ value, options, placeholder, ariaLabel, onChange, disabled = false, searchable = false, hideSecondary = false }: { value: string; options: WorkflowSelectOption[]; placeholder: string; ariaLabel: string; onChange: (value: string) => void; disabled?: boolean; searchable?: boolean; hideSecondary?: boolean }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const pickerSearchEnabled = searchable || ariaLabel === "Agent" || ariaLabel === "Published tool version";
  const pickerSecondaryHidden = hideSecondary || ariaLabel === "Published tool version";
  const selectedIndex = options.findIndex((option) => option.value === value);
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : null;
  const visibleOptions = pickerSearchEnabled && query.trim()
    ? options.filter((option) => `${option.label} ${option.secondary ?? ""}`.toLowerCase().includes(query.trim().toLowerCase()))
    : options;
  const selectedVisibleIndex = visibleOptions.findIndex((option) => option.value === value);
  const [highlightedIndex, setHighlightedIndex] = useState(Math.max(selectedVisibleIndex, 0));

  useEffect(() => {
    if (selectedVisibleIndex >= 0) setHighlightedIndex(selectedVisibleIndex);
    else setHighlightedIndex(0);
  }, [selectedVisibleIndex]);
  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: MouseEvent) => { if (rootRef.current && !rootRef.current.contains(event.target as globalThis.Node)) { setOpen(false); setQuery(""); } };
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open, pickerSearchEnabled]);

  function chooseOption(option?: WorkflowSelectOption) {
    if (!option) return;
    onChange(option.value);
    setOpen(false);
    setQuery("");
  }

  function moveHighlight(direction: 1 | -1) {
    if (visibleOptions.length === 0) return;
    setHighlightedIndex((index) => (index + direction + visibleOptions.length) % visibleOptions.length);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (disabled || options.length === 0) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) { setOpen(true); return; }
      moveHighlight(event.key === "ArrowDown" ? 1 : -1);
    } else if ((event.key === "Enter" || event.key === " ") && open) {
      event.preventDefault(); chooseOption(visibleOptions[highlightedIndex]);
    } else if (event.key === "Escape" && open) { event.preventDefault(); setOpen(false); setQuery(""); }
  }

  function handleSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") { event.preventDefault(); moveHighlight(1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); moveHighlight(-1); }
    else if (event.key === "Enter") { event.preventDefault(); chooseOption(visibleOptions[highlightedIndex]); }
    else if (event.key === "Escape") { event.preventDefault(); setOpen(false); setQuery(""); }
  }

  return <div className="model-select workflow-select" ref={rootRef}><button className="model-select-trigger" type="button" aria-label={ariaLabel} aria-haspopup="listbox" aria-expanded={open} aria-controls={listboxId} disabled={disabled || options.length === 0} onClick={() => { setOpen((current) => !current); if (open) setQuery(""); }} onKeyDown={handleKeyDown}><span className={selectedOption ? "model-select-value" : "model-select-placeholder"}>{selectedOption?.label || placeholder}</span><ChevronDown className={open ? "model-select-chevron open" : "model-select-chevron"} size={17} aria-hidden="true" /></button>{open ? <div className="model-select-menu" id={listboxId} role="listbox" aria-label={ariaLabel}>{pickerSearchEnabled ? <label className="model-select-search"><Search size={15} aria-hidden="true" /><span className="sr-only">Search {ariaLabel.toLowerCase()}</span><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={handleSearchKeyDown} placeholder={`Search ${ariaLabel.toLowerCase()}…`} autoComplete="off" /></label> : null}{visibleOptions.length > 0 ? visibleOptions.map((option, index) => <button className={index === highlightedIndex ? "model-select-option highlighted" : "model-select-option"} key={option.value} type="button" role="option" aria-selected={option.value === value} onMouseEnter={() => setHighlightedIndex(index)} onClick={() => chooseOption(option)}><span><strong>{option.label}</strong>{!pickerSecondaryHidden && option.secondary ? <small>{option.secondary}</small> : null}</span>{option.value === value ? <Check size={16} aria-hidden="true" /> : null}</button>) : <div className="model-select-empty">No matching {ariaLabel.toLowerCase()} found.</div>}</div> : null}</div>;
}

export function WorkflowEditor({ workflowId, initialDraft, latestVersionId, agentsLoading = false, agents = [], agentVersions = [], tools = [] }: { workflowId: string; initialDraft: WorkflowDraft; latestVersionId?: string | null; agentsLoading?: boolean; agents?: Agent[]; agentVersions?: AgentVersionSummary[]; tools?: Tool[] }) {
  const [definition, setDefinition] = useState(initialDraft.definition);
  const initial = useMemo(() => toCanvas(initialDraft.definition), [initialDraft.definition]);
  const [nodes, setNodes] = useState<CanvasNode[]>(initial.nodes);
  const [edges, setEdges] = useState<Edge[]>(initial.edges);
  const [revision, setRevision] = useState(initialDraft.revision);
  const [selected, setSelected] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [paletteDragActive, setPaletteDragActive] = useState(false);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<CanvasNode, Edge> | null>(null);
  const [validation, setValidation] = useState<{ valid: boolean; errors: Array<{ code: string; message: string; node_key?: string; field?: string }> } | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<FeedbackToastState | null>(null);
  const [publishedVersionId, setPublishedVersionId] = useState<string | null>(latestVersionId ?? null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [agentSelectionByNode, setAgentSelectionByNode] = useState<Record<string, string>>({});
  const [runInputOpen, setRunInputOpen] = useState(false);
  const [runInputFields, setRunInputFields] = useState<RunInputField[]>([
    { id: "input-field-1", key: "topic", value: "", type: "text" },
  ]);

  useEffect(() => setDefinition((current) => toDefinition(nodes, edges, current)), [nodes, edges]);
  useEffect(() => {
    if (!runInputOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) setRunInputOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [busy, runInputOpen]);
  const activeNode = nodes.find((node) => node.id === selected);
  function workflowErrorMessage(reason: unknown, fallback: string) {
    if (!(reason instanceof ApiRequestError)) return reason instanceof Error ? reason.message : fallback;
    const errors = Array.isArray(reason.details.errors) ? reason.details.errors : [];
    const nodeLabels = errors
      .filter((item): item is { message?: string; node_key?: string; field?: string } => Boolean(item && typeof item === "object"))
      .slice(0, 4)
      .map((item) => {
        const node = nodes.find((candidate) => candidate.id === item.node_key);
        const location = [node?.data.label ?? item.node_key, item.field].filter(Boolean).join(" · ");
        return `${location ? `${location}: ` : ""}${item.message || "Invalid configuration."}`;
      });
    return nodeLabels.length > 0 ? `${reason.summary} ${nodeLabels.join(" | ")}` : reason.message;
  }

  function validationFromError(reason: unknown) {
    if (!(reason instanceof ApiRequestError) || !Array.isArray(reason.details.errors)) return null;
    return reason.details.errors
      .filter((item): item is { code?: string; message?: string; node_key?: string; field?: string } => Boolean(item && typeof item === "object"))
      .map((item) => ({ code: item.code || "INVALID_CONFIGURATION", message: `${item.field ? `${item.field}: ` : ""}${item.message || "Invalid configuration."}`, node_key: item.node_key, field: item.field }));
  }
  useEffect(() => {
    const agentNode = nodes.find((node) => node.id === selected && node.data.type === "AGENT");
    const agentId = agentNode ? agentSelectionByNode[agentNode.id] : undefined;
    if (!agentNode || !agentId) return;
    const currentVersion = agentVersions.find((version) => version.id === agentNode.data.config.agent_version_id);
    if (currentVersion?.agent_id === agentId) return;
    const latestVersion = agentVersions
      .filter((version) => version.agent_id === agentId)
      .sort((left, right) => right.version_number - left.version_number)[0];
    if (!latestVersion) return;
    setNodes((current) => current.map((node) => node.id === agentNode.id
      ? { ...node, data: { ...node.data, config: { ...node.data.config, agent_version_id: latestVersion.id } } }
      : node));
  }, [agentSelectionByNode, agentVersions, nodes, selected]);
  const onNodesChange: OnNodesChange<CanvasNode> = useCallback((changes) => {
    const deletedNodeKeys = new Set(changes.filter((change) => change.type === "remove").map((change) => change.id));
    setNodes((current) => {
      const next = applyNodeChanges(changes, current) as CanvasNode[];
      if (deletedNodeKeys.size === 0) return next;
      return next.map((node) => ({
        ...node,
        data: {
          ...node.data,
          config: resetDeletedNodeReferences(node.data.config, deletedNodeKeys) as Record<string, unknown>,
        },
      }));
    });
    if (deletedNodeKeys.size > 0) {
      setEdges((current) => current.filter((edge) => !deletedNodeKeys.has(edge.source) && !deletedNodeKeys.has(edge.target)));
    }
  }, []);
  const onEdgesChange: OnEdgesChange = useCallback((changes) => setEdges((current) => applyEdgeChanges(changes, current)), []);
  const onConnect = useCallback((connection: Connection) => setEdges((current) => addEdge({ ...connection, type: "smoothstep" }, current)), []);

  async function save(showSuccess = true, manageBusy = true): Promise<boolean> {
    if (manageBusy) setBusy(true);
    setToast({ kind: "loading", message: "Saving workflow draft…" });
    try {
      // Build from the latest canvas state instead of waiting for the
      // nodes/edges effect to publish its next definition snapshot. This keeps
      // an immediate Save click from sending the previous config to the API.
      const currentDefinition = toDefinition(nodes, edges, definition);
      const result = await saveWorkflowDraft(workflowId, revision, currentDefinition);
      setRevision(result.revision);
      setDefinition(result.definition);
      if (showSuccess) setToast({ kind: "success", message: "Draft saved." });
      return true;
    } catch (reason: unknown) {
      const issues = validationFromError(reason);
      if (issues?.length) setValidation({ valid: false, errors: issues });
      setToast({ kind: "error", message: workflowErrorMessage(reason, "Unable to save draft.") });
      return false;
    } finally {
      if (manageBusy) setBusy(false);
    }
  }

  async function validate() {
    setBusy(true);
    setToast({ kind: "loading", message: "Validating workflow…" });
    try {
      const result = await validateWorkflowDraft(workflowId);
      setValidation({
        ...result,
        errors: result.errors.map((issue) => ({
          ...issue,
          message: `${issue.field ? `${issue.field}: ` : ""}${issue.message}`,
        })),
      });
      setToast(result.valid
        ? { kind: "success", message: "Workflow is valid." }
        : { kind: "error", message: `${result.errors.length} validation issue${result.errors.length === 1 ? "" : "s"} found.` });
    } catch (reason: unknown) {
      setToast({ kind: "error", message: workflowErrorMessage(reason, "Unable to validate workflow.") });
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    setBusy(true);
    setToast({ kind: "loading", message: "Saving and publishing workflow…" });
    try {
      if (!await save(false, false)) return;
      const result = await publishWorkflow(workflowId);
      setPublishedVersionId(result.id);
      setToast({ kind: "success", message: `Published version ${result.version_number}.` });
    } catch (reason: unknown) {
      const issues = validationFromError(reason);
      if (issues?.length) setValidation({ valid: false, errors: issues });
      setToast({ kind: "error", message: workflowErrorMessage(reason, "Unable to publish workflow.") });
    } finally {
      setBusy(false);
    }
  }

  function openRunDialog() {
    if (!publishedVersionId) {
      setToast({ kind: "error", message: "Publish a version before running the workflow." });
      return;
    }
    setRunInputOpen(true);
    setToast(null);
  }

  function updateRunInputField(id: string, patch: Partial<RunInputField>) {
    setRunInputFields((current) => current.map((field) => field.id === id ? { ...field, ...patch } : field));
  }

  function addRunInputField() {
    setRunInputFields((current) => [...current, { id: `input-field-${Date.now()}`, key: "", value: "", type: "text" }]);
  }

  function removeRunInputField(id: string) {
    setRunInputFields((current) => current.filter((field) => field.id !== id));
  }

  function buildRunInput() {
    const input: Record<string, unknown> = {};
    for (const field of runInputFields) {
      const key = field.key.trim();
      if (!key) {
        setToast({ kind: "error", message: "Every workflow input needs a field name." });
        return null;
      }
      if (Object.prototype.hasOwnProperty.call(input, key)) {
        setToast({ kind: "error", message: `The input field “${key}” is duplicated.` });
        return null;
      }
      if (field.type === "number") {
        const numberValue = Number(field.value);
        if (!field.value.trim() || Number.isNaN(numberValue)) {
          setToast({ kind: "error", message: `Enter a valid number for “${key}”.` });
          return null;
        }
        input[key] = numberValue;
      } else if (field.type === "boolean") {
        input[key] = field.value === "true";
      } else {
        input[key] = field.value;
      }
    }
    return input;
  }

  async function executeRun() {
    if (!publishedVersionId) return;
    const input = buildRunInput();
    if (!input) return;
    setBusy(true);
    setRunInputOpen(false);
    setToast({ kind: "loading", message: "Starting workflow run…" });
    try {
      const result = await runWorkflow(workflowId, publishedVersionId, input);
      window.location.href = `/workflow-runs/${result.id}`;
    } catch (reason: unknown) {
      setToast({ kind: "error", message: workflowErrorMessage(reason, "Unable to start workflow run.") });
      setBusy(false);
    }
  }

  function addNode(type: DefinitionNode["type"], position?: { x: number; y: number }) { const key = `${type.toLowerCase()}-${Date.now().toString(36)}-${nodes.length + 1}`; const config: Record<string, unknown> = type === "AGENT" ? { input: { kind: "ref", scope: "input", path: "" } } : type === "TOOL" ? { arguments: [] } : type === "CONDITION" ? { expression: { op: "exists", value: { kind: "ref", scope: "input", path: "" } } } : type === "END" ? { output: { kind: "ref", scope: "variables", path: "" } } : {};
    setNodes((current) => [...current, { id: key, type: "workflow", position: position ?? { x: 260 + current.length * 30, y: 120 + current.length * 20 }, data: { label: typeLabels[type], type, config } }]);
    setSelected(key);
    setInspectorOpen(true);
  }

  function handlePaletteDragStart(event: React.DragEvent<HTMLButtonElement>, type: DefinitionNode["type"]) {
    event.dataTransfer.effectAllowed = "copy";
    event.dataTransfer.setData("application/vibesfactory-workflow-node", type);
  }

  function handleCanvasDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setPaletteDragActive(false);
    const type = event.dataTransfer.getData("application/vibesfactory-workflow-node") as DefinitionNode["type"];
    if (!flowInstance || !Object.prototype.hasOwnProperty.call(typeLabels, type)) return;
    addNode(type, flowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY }));
  }

  function updateNodeConfig(patch: Record<string, unknown>) { if (!activeNode) return; const nextConfig = { ...activeNode.data.config, ...patch }; setNodes((current) => current.map((node) => node.id === activeNode.id ? { ...node, data: { ...node.data, config: nextConfig } } : node)); }
  function updateNodeLabel(label: string) { if (!activeNode) return; setNodes((current) => current.map((node) => node.id === activeNode.id ? { ...node, data: { ...node.data, label } } : node)); }

  const nodeRefs = nodes.filter((node) => node.id !== activeNode?.id).map((node) => ({ value: node.id, label: node.data.label }));
  const renderRefFields = (value: unknown, onChange: (next: ExpressionValue) => void, idPrefix: string, description: string) => {
    return renderExpressionFields(value, onChange, idPrefix, description);
  };

  const renderExpressionFields = (value: unknown, onChange: (next: ExpressionValue) => void, idPrefix: string, description: string) => {
    const expression = readExpression(value, { kind: "ref", scope: "input", path: "" });
    const mode = expression.kind === "literal" ? "literal" : expression.scope;
    const modeOptions: WorkflowSelectOption[] = [
      { value: "literal", label: "Fixed value", secondary: "Type a value that is always sent unchanged" },
      { value: "input", label: "Workflow input", secondary: "A field supplied when the run starts" },
      { value: "variables", label: "Workflow variables", secondary: "A value created by an earlier transform" },
      { value: "node", label: "Previous node output", secondary: "Output from a completed node" },
    ];
    const literalType = typeof expression.kind === "string" && expression.kind === "literal"
      ? typeof expression.value === "number" ? "number" : typeof expression.value === "boolean" ? "boolean" : "text"
      : "text";
    const updateMode = (nextMode: string) => {
      if (nextMode === "literal") {
        onChange({ kind: "literal", value: expression.kind === "literal" ? expression.value : "" });
        return;
      }
      const previous = expression.kind === "ref" ? expression : null;
      onChange({ kind: "ref", scope: nextMode as RefScope, path: previous?.path ?? "", ...(nextMode === "node" ? { node_key: previous?.node_key ?? nodeRefs[0]?.value ?? "" } : {}) });
    };
    const updateLiteralType = (nextType: string) => {
      const current = expression.kind === "literal" ? expression.value : "";
      onChange({ kind: "literal", value: nextType === "number" ? (typeof current === "number" ? current : 0) : nextType === "boolean" ? Boolean(current) : String(current ?? "") });
    };
    const nodeResultOptions: WorkflowSelectOption[] = [
      { value: "", label: "Complete result", secondary: "Pass everything returned by the previous node" },
      { value: "/text", label: "Response text", secondary: "The written answer from an agent" },
      { value: "/output/value", label: "Returned value", secondary: "The main value produced by a tool" },
      { value: "/output", label: "Tool result", secondary: "All data returned by a tool" },
    ];
    const currentNodePath = expression.kind === "ref" ? toPointer(expression.path) : "";
    const visibleNodeResultOptions = nodeResultOptions.some((option) => option.value === currentNodePath)
      ? nodeResultOptions
      : [...nodeResultOptions, { value: currentNodePath, label: "Custom result field", secondary: "A saved field from this node" }];
    return <div className="workflow-mapping-card workflow-expression-card">
      <div className="workflow-field-heading"><span><Database size={14} aria-hidden="true" />{description}</span><small>Choose a clear value source</small></div>
      <label className="form-label">Source<WorkflowSelect value={mode} options={modeOptions} placeholder="Choose a source" ariaLabel={`${description} source`} onChange={updateMode} /></label>
      {mode === "literal" ? <>
        <label className="form-label">Value type<WorkflowSelect value={literalType} options={[{ value: "text", label: "Text", secondary: "A sentence, topic or prompt" }, { value: "number", label: "Number", secondary: "A numeric value" }, { value: "boolean", label: "True / false", secondary: "A yes or no value" }]} placeholder="Choose a value type" ariaLabel={`${description} value type`} onChange={updateLiteralType} /></label>
        {literalType === "boolean" ? <label className="form-label">Value<WorkflowSelect value={String(expression.kind === "literal" && expression.value === true)} options={[{ value: "true", label: "True", secondary: "Pass yes / enabled" }, { value: "false", label: "False", secondary: "Pass no / disabled" }]} placeholder="Choose true or false" ariaLabel={`${description} boolean value`} onChange={(next) => onChange({ kind: "literal", value: next === "true" })} /></label> : <label className="form-label">Value{literalType === "text" ? <textarea rows={3} value={String(expression.kind === "literal" ? expression.value ?? "" : "")} onChange={(event) => onChange({ kind: "literal", value: event.target.value })} placeholder="For example: Research workflow orchestration" /> : <input type="number" value={String(expression.kind === "literal" ? expression.value ?? "" : "")} onChange={(event) => onChange({ kind: "literal", value: event.target.value === "" ? "" : Number(event.target.value) })} placeholder="For example: 3" />}</label>}
        <small className="workflow-helper">Fixed value means the workflow sends exactly what you enter here. It is stored as a JSON expression automatically.</small>
      </> : <>
        {mode === "node" ? <label className="form-label">Node<WorkflowSelect value={expression.kind === "ref" ? expression.node_key ?? "" : ""} options={nodeRefs.map((node) => ({ value: node.value, label: node.label, secondary: "Completed node output" }))} placeholder="Choose a previous node" ariaLabel={`${description} previous node`} onChange={(nodeKey) => onChange({ kind: "ref", scope: "node", node_key: nodeKey, path: expression.kind === "ref" ? expression.path : "" })} disabled={nodeRefs.length === 0} /></label> : null}
        {mode === "node" ? <label className="form-label">Result to pass<WorkflowSelect value={currentNodePath} options={visibleNodeResultOptions} placeholder="Choose which result to pass" ariaLabel={`${description} result field`} onChange={(path) => onChange({ kind: "ref", scope: "node", path, ...(expression.kind === "ref" && expression.node_key ? { node_key: expression.node_key } : nodeRefs[0] ? { node_key: nodeRefs[0].value } : {}) })} /><small>Choose the part of the previous node result that this step needs.</small></label> : <label className="form-label">{mode === "input" ? "Workflow input field" : "Workflow variable field"}<input id={`${idPrefix}-path`} value={editablePath(expression.kind === "ref" ? expression.path : "")} onChange={(event) => onChange({ kind: "ref", scope: mode as RefScope, path: toFriendlyPath(event.target.value) })} placeholder={mode === "input" ? "For example: Topic" : "For example: Research topic"} /><small>{expression.kind === "ref" && expression.path ? `Selected field: ${humanizePath(expression.path)}. Saved as a workflow field automatically.` : `Enter the ${mode === "input" ? "input field" : "variable field"} this step should use.`}</small></label>}
      </>}
    </div>;
  };

  const renderAgentConfig = () => { if (!activeNode) return null; const config = activeNode.data.config; const selectedAgentVersion = String(config.agent_version_id ?? ""); const selectedVersionRecord = agentVersions.find((version) => version.id === selectedAgentVersion); const selectedAgentId = agentSelectionByNode[activeNode.id] ?? selectedVersionRecord?.agent_id ?? ""; const agentOptions: WorkflowSelectOption[] = agents.map((agent) => ({ value: agent.id, label: agent.name, secondary: agent.latest_version_number > 0 ? `${agent.latest_version_number} published version${agent.latest_version_number === 1 ? "" : "s"}` : "No published versions yet" })); const versionOptions: WorkflowSelectOption[] = agentVersions.filter((version) => version.agent_id === selectedAgentId).map((version) => ({ value: version.id, label: `Version ${version.version_number}`, secondary: version.change_note || "Immutable published configuration" })); return <div className="workflow-config-stack"><label className="form-label">Agent<span className="required-mark">*</span><WorkflowSelect value={selectedAgentId} options={agentOptions} placeholder={agentsLoading ? "Loading agents…" : agents.length > 0 ? "Select an agent" : "No agents available"} ariaLabel="Agent" onChange={(agentId) => { setAgentSelectionByNode((current) => ({ ...current, [activeNode.id]: agentId })); updateNodeConfig({ agent_version_id: "" }); }} disabled={agentsLoading} /></label>{selectedAgentId ? <label className="form-label">Published version<span className="required-mark">*</span><WorkflowSelect value={selectedAgentVersion} options={versionOptions} placeholder={versionOptions.length ? "Select a published version" : "No published versions"} ariaLabel="Published agent version" onChange={(versionId) => updateNodeConfig({ agent_version_id: versionId })} disabled={agentsLoading || versionOptions.length === 0} /></label> : <div className="workflow-selection-hint" role={agentsLoading ? "status" : undefined}>{agentsLoading ? <LoaderCircle className="spin" size={14} aria-hidden="true" /> : <Info size={14} aria-hidden="true" />}<span>{agentsLoading ? "Loading agents and published versions…" : agents.length === 0 ? "No agents are available in this workflow’s workspace. Create and publish one first." : "Choose an agent first. Its published versions will appear here."}</span>{!agentsLoading && agents.length === 0 ? <Link className="text-button" href="/agents">Open Agents</Link> : null}</div>}<small className="workflow-field-note">Runs pin this exact version, so future agent edits cannot change an existing workflow.</small>{renderRefFields(config.input, (next) => updateNodeConfig({ input: next }), `${activeNode.id}-input`, "Agent input")}</div>; };

  const renderToolConfig = () => { if (!activeNode) return null; const config = activeNode.data.config; const argumentList = Array.isArray(config.arguments) ? config.arguments as Array<{ target?: string; value?: unknown }> : []; const versions: WorkflowSelectOption[] = tools.flatMap((tool) => tool.versions.map((version) => ({ value: version.id, label: `${tool.name} · v${version.version_number}`, secondary: tool.description || `${tool.type} tool` }))); const sourceOptions: WorkflowSelectOption[] = [{ value: "input", label: "Workflow input" }, { value: "variables", label: "Workflow variables" }, { value: "node", label: "Previous node output" }]; const addArgument = () => updateNodeConfig({ arguments: [...argumentList, { target: "", value: { kind: "ref", scope: "input", path: "" } }] }); const removeArgument = (index: number) => updateNodeConfig({ arguments: argumentList.filter((_, itemIndex) => itemIndex !== index) }); const updateArgument = (index: number, patch: Record<string, unknown>) => updateNodeConfig({ arguments: argumentList.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) }); return <div className="workflow-config-stack"><label className="form-label">Tool version<span className="required-mark">*</span><WorkflowSelect value={String(config.tool_version_id ?? "")} options={versions} placeholder="Select a published tool version" ariaLabel="Published tool version" onChange={(toolVersionId) => updateNodeConfig({ tool_version_id: toolVersionId })} /><small>Only published versions can run. High-risk and side-effect tools remain fail-closed.</small></label><div className="workflow-section-heading"><span>Argument mapping</span><button className="text-button" type="button" onClick={addArgument}><Plus size={14} aria-hidden="true" />Add mapping</button></div>{argumentList.length === 0 ? <div className="workflow-empty-config"><Info size={15} aria-hidden="true" /><span>Add a mapping when the tool expects input. The left field is the tool argument name.</span></div> : argumentList.map((argument, index) => { const ref = readRef(argument.value, { kind: "ref", scope: "input", path: "" }); return <div className="workflow-argument-row" key={`${activeNode.id}-argument-${index}`}><label className="form-label"><span>Argument name</span><input value={displayPath(argument.target ?? "")} onChange={(event) => updateArgument(index, { target: toPointer(event.target.value) })} placeholder="query" /></label><label className="form-label"><span>Value from</span><WorkflowSelect value={ref.scope} options={sourceOptions} placeholder="Choose a source" ariaLabel="Tool argument source" onChange={(scope) => updateArgument(index, { value: { ...ref, scope: scope as RefScope, ...(scope === "node" ? { node_key: nodeRefs[0]?.value ?? "" } : {}) } })} /></label>{ref.scope === "node" ? <label className="form-label workflow-argument-node"><span>Node</span><WorkflowSelect value={ref.node_key ?? ""} options={nodeRefs.map((node) => ({ value: node.value, label: node.label }))} placeholder="Choose a node" ariaLabel="Tool argument node" onChange={(nodeKey) => updateArgument(index, { value: { ...ref, node_key: nodeKey } })} disabled={nodeRefs.length === 0} /></label> : null}<label className="form-label"><span>Input field</span><input value={displayPath(ref.path)} onChange={(event) => updateArgument(index, { value: { ...ref, path: toPointer(event.target.value) } })} placeholder="topic or query" /></label><button className="icon-button danger workflow-remove-argument" type="button" aria-label={`Remove ${displayPath(argument.target || "argument")} mapping`} onClick={() => removeArgument(index)}><Trash2 size={15} aria-hidden="true" /></button></div>; })}</div>; };

  const renderConditionConfig = () => { if (!activeNode) return null; const config = activeNode.data.config; const expression = config.expression && typeof config.expression === "object" ? config.expression as Record<string, unknown> : { op: "exists", value: { kind: "ref", scope: "input", path: "" } }; const operator = String(expression.op ?? "exists"); const operatorOptions: WorkflowSelectOption[] = [{ value: "exists", label: "Has a value", secondary: "Continue when a value is present" }, { value: "eq", label: "Equals", secondary: "Compare two values" }, { value: "neq", label: "Does not equal" }, { value: "contains", label: "Contains" }, { value: "gt", label: "Greater than" }, { value: "gte", label: "Greater than or equal" }, { value: "lt", label: "Less than" }, { value: "lte", label: "Less than or equal" }, { value: "all", label: "All conditions", secondary: "Advanced nested expression" }, { value: "any", label: "Any condition", secondary: "Advanced nested expression" }, { value: "not", label: "Not", secondary: "Advanced nested expression" }]; const setOperator = (nextOperator: string) => { if (nextOperator === "exists") updateNodeConfig({ expression: { op: nextOperator, value: expression.value ?? { kind: "ref", scope: "input", path: "" } } }); else updateNodeConfig({ expression: { op: nextOperator, left: expression.left ?? { kind: "ref", scope: "input", path: "" }, right: expression.right ?? { kind: "ref", scope: "variables", path: "" } } }); }; return <div className="workflow-config-stack"><label className="form-label">Rule<WorkflowSelect value={operator} options={operatorOptions} placeholder="Choose a rule" ariaLabel="Condition rule" onChange={setOperator} /></label>{operator === "exists" ? renderRefFields(expression.value, (next) => updateNodeConfig({ expression: { op: "exists", value: next } }), `${activeNode.id}-condition-value`, "Value to check") : ["eq", "neq", "contains", "gt", "gte", "lt", "lte"].includes(operator) ? <><div className="workflow-condition-caption">Compare these two values</div>{renderRefFields(expression.left, (next) => updateNodeConfig({ expression: { ...expression, op: operator, left: next } }), `${activeNode.id}-condition-left`, "Left value")}{renderRefFields(expression.right, (next) => updateNodeConfig({ expression: { ...expression, op: operator, right: next } }), `${activeNode.id}-condition-right`, "Right value")}</> : <div className="workflow-selection-hint"><Info size={14} aria-hidden="true" /><span>Nested condition groups are available in advanced configuration. The safe expression DSL is validated before publish.</span></div>}</div>; };

  const renderTransformConfig = () => {
    if (!activeNode) return null;
    const config = activeNode.data.config;
    const assignments = Array.isArray(config.assignments)
      ? config.assignments as Array<{ target?: string; value?: unknown }>
      : [];
    const sourceOptions: WorkflowSelectOption[] = [
      { value: "literal", label: "Fixed value", secondary: "Enter a value that is always sent unchanged" },
      { value: "input", label: "Workflow input" },
      { value: "variables", label: "Workflow variables" },
      { value: "node", label: "Previous node output" },
    ];
    const nodeResultOptions: WorkflowSelectOption[] = [
      { value: "", label: "Complete result", secondary: "Pass everything returned by the previous node" },
      { value: "/text", label: "Response text", secondary: "The written answer from an agent" },
      { value: "/output/value", label: "Returned value", secondary: "The main value produced by a tool" },
      { value: "/output", label: "Tool result", secondary: "All data returned by a tool" },
    ];
    const updateAssignments = (nextAssignments: Array<{ target?: string; value?: unknown }>) => updateNodeConfig({ assignments: nextAssignments });

    return <div className="workflow-config-stack">
      <div className="workflow-section-heading"><span>Set variables</span><button className="text-button" type="button" onClick={() => updateAssignments([...assignments, { target: "", value: { kind: "ref", scope: "input", path: "" } }])}><Plus size={14} aria-hidden="true" />Add field</button></div>
      {assignments.length === 0 ? <div className="workflow-empty-config"><Info size={15} aria-hidden="true" /><span>Add a field to copy a value into workflow variables.</span></div> : assignments.map((assignment, index) => {
        const expression = readExpression(assignment.value, { kind: "ref", scope: "input", path: "" });
        const ref = expression.kind === "ref" ? expression : { kind: "ref" as const, scope: "input" as const, path: "" };
        const valueSource = expression.kind === "literal" ? "literal" : ref.scope;
        const literalType = expression.kind === "literal"
          ? typeof expression.value === "number" ? "number" : typeof expression.value === "boolean" ? "boolean" : "text"
          : "text";
        const currentNodePath = toPointer(ref.path);
        const visibleNodeResultOptions = nodeResultOptions.some((option) => option.value === currentNodePath)
          ? nodeResultOptions
          : [...nodeResultOptions, { value: currentNodePath, label: "Custom result field", secondary: "A saved field from this node" }];
        const updateAssignment = (patch: Record<string, unknown>) => updateAssignments(assignments.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
        const updateSource = (scope: string) => updateAssignment({ value: scope === "literal" ? { kind: "literal", value: expression.kind === "literal" ? expression.value : "" } : { ...ref, scope: scope as RefScope, ...(scope === "node" ? { node_key: ref.node_key ?? nodeRefs[0]?.value ?? "" } : {}) } });
        const updateLiteralType = (nextType: string) => {
          const current = expression.kind === "literal" ? expression.value : "";
          updateAssignment({ value: { kind: "literal", value: nextType === "number" ? (typeof current === "number" ? current : 0) : nextType === "boolean" ? Boolean(current) : String(current ?? "") } });
        };
        return <div className="workflow-transform-row" key={`${activeNode.id}-assignment-${index}`}>
          <label className="form-label"><span>Output field</span><input value={editablePath(assignment.target ?? "")} onChange={(event) => updateAssignment({ target: toFriendlyPath(event.target.value) })} placeholder="For example: Research topic" /><small>{assignment.target ? `Saved as: ${humanizePath(assignment.target)}. The JSON path is generated automatically.` : "Give this value a readable name for later steps."}</small></label>
          <label className="form-label"><span>Value source</span><WorkflowSelect value={valueSource} options={sourceOptions} placeholder="Choose a source" ariaLabel="Transform value source" onChange={updateSource} /></label>
          {valueSource === "literal" ? <>
            <label className="form-label"><span>Value type</span><WorkflowSelect value={literalType} options={[{ value: "text", label: "Text", secondary: "A sentence, topic or prompt" }, { value: "number", label: "Number", secondary: "A numeric value" }, { value: "boolean", label: "True / false", secondary: "A yes or no value" }]} placeholder="Choose a value type" ariaLabel="Transform fixed value type" onChange={updateLiteralType} /></label>
            {literalType === "boolean" ? <label className="form-label"><span>Fixed value</span><WorkflowSelect value={String(expression.kind === "literal" && expression.value === true)} options={[{ value: "true", label: "True", secondary: "Pass yes / enabled" }, { value: "false", label: "False", secondary: "Pass no / disabled" }]} placeholder="Choose true or false" ariaLabel="Transform fixed boolean value" onChange={(next) => updateAssignment({ value: { kind: "literal", value: next === "true" } })} /></label> : <label className="form-label"><span>Fixed value</span>{literalType === "text" ? <textarea rows={3} value={String(expression.kind === "literal" ? expression.value ?? "" : "")} onChange={(event) => updateAssignment({ value: { kind: "literal", value: event.target.value } })} placeholder="For example: Research workflow orchestration" /> : <input type="number" value={String(expression.kind === "literal" ? expression.value ?? "" : "")} onChange={(event) => updateAssignment({ value: { kind: "literal", value: event.target.value === "" ? "" : Number(event.target.value) } })} placeholder="For example: 3" />}</label>}
            <small className="workflow-helper">This value is stored directly in the transform output and does not depend on another node.</small>
          </> : ref.scope === "node" ? <>
            <label className="form-label"><span>Previous node</span><WorkflowSelect value={ref.node_key ?? ""} options={nodeRefs.map((node) => ({ value: node.value, label: node.label, secondary: "Completed node output" }))} placeholder="Choose a previous node" ariaLabel="Transform previous node" onChange={(nodeKey) => updateAssignment({ value: { ...ref, scope: "node", node_key: nodeKey } })} disabled={nodeRefs.length === 0} /></label>
            <label className="form-label"><span>Result field</span><WorkflowSelect value={currentNodePath} options={visibleNodeResultOptions} placeholder="Choose a result field" ariaLabel="Transform result field" onChange={(path) => updateAssignment({ value: { ...ref, scope: "node", path, ...(ref.node_key ? { node_key: ref.node_key } : nodeRefs[0] ? { node_key: nodeRefs[0].value } : {}) } })} /><small>Choose the part of the previous node result to save.</small></label>
          </> : <label className="form-label"><span>{ref.scope === "input" ? "Workflow input field" : "Workflow variable field"}</span><input value={editablePath(ref.path)} onChange={(event) => updateAssignment({ value: { ...ref, path: toFriendlyPath(event.target.value) } })} placeholder={ref.scope === "input" ? "For example: Topic" : "For example: Research topic"} /><small>{ref.path ? `Selected field: ${humanizePath(ref.path)}. Saved as a workflow field automatically.` : `Enter the ${ref.scope === "input" ? "input field" : "variable field"} to copy.`}</small></label>}
          <button className="icon-button danger workflow-remove-argument" type="button" aria-label="Remove variable mapping" onClick={() => updateAssignments(assignments.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={15} aria-hidden="true" /></button>
        </div>;
      })}
      <small className="workflow-field-note">Choose values using plain-language fields. The editor converts them into JSON Pointer paths for the workflow contract.</small>
    </div>;
  };

  const renderEndConfig = () => { if (!activeNode) return null; return <div className="workflow-config-stack"><div className="workflow-section-heading"><span>Final output</span></div>{renderRefFields(activeNode.data.config.output, (next) => updateNodeConfig({ output: next }), `${activeNode.id}-output`, "Value returned by the workflow")}</div>; };

  const renderSimpleConfig = () => <div className="workflow-empty-config workflow-simple-config"><Info size={15} aria-hidden="true" /><span>{activeNode?.data.type === "START" ? "This node receives the input object supplied when the workflow run starts." : "This node has no basic fields to configure. Use advanced configuration only when you need a custom expression."}</span></div>;
  const renderApprovalConfig = () => { if (!activeNode) return null; const config = activeNode.data.config; return <div className="workflow-config-stack"><label className="form-label"><span>Approval message</span><textarea rows={3} value={String(config.message ?? "") } onChange={(event) => updateNodeConfig({ message: event.target.value })} placeholder="Approve sending this customer notification?" /><small>Explain the action and consequence to the reviewer.</small></label><label className="form-label"><span>Approval TTL (seconds)</span><input type="number" min={300} max={604800} value={String(config.ttl_seconds ?? 86400)} onChange={(event) => updateNodeConfig({ ttl_seconds: Number(event.target.value) })} /><small>Default 24 hours. Allowed range: 5 minutes to 7 days.</small></label><div className="workflow-empty-config"><ShieldCheck size={15} aria-hidden="true" /><span>Connect the approved and rejected handles to make the decision explicit.</span></div></div>; };

  return <ReactFlowProvider><div className="workflow-editor-shell">
    <div className="workflow-editor-toolbar"><div className="workflow-editor-toolbar-title"><span className="eyebrow">Workflow editor</span><strong>Draft · revision {revision}</strong><small>Build a deterministic flow, then validate before publishing.</small></div><div className="workflow-toolbar-actions"><button className="button subtle-button" type="button" onClick={() => { setNodes((current) => autoLayout(current, edges)); setToast({ kind: "success", message: "Canvas auto-arranged." }); }} disabled={busy}><LayoutGrid size={15} aria-hidden="true" />Auto layout</button><button className="button subtle-button" type="button" onClick={() => void validate()} disabled={busy}><ShieldCheck size={15} aria-hidden="true" />Validate</button><button className="button subtle-button" type="button" onClick={() => void save()} disabled={busy}><Save size={15} aria-hidden="true" />Save</button><button className="button subtle-button" type="button" onClick={() => void publish()} disabled={busy}><Sparkles size={15} aria-hidden="true" />Publish</button><button className="button primary-button" type="button" onClick={openRunDialog} disabled={busy}><Play size={15} aria-hidden="true" />Run</button></div></div>
    <FeedbackToast toast={toast} onDismiss={() => setToast(null)} />
    <div className={`workflow-editor-body ${inspectorOpen ? "" : "inspector-collapsed"}`}>
      <aside className="workflow-palette">
        <div className="workflow-panel-heading"><span className="panel-label">Node palette</span><small>Click or drag</small></div>
        {(["START", "AGENT", "TOOL", "CONDITION", "APPROVAL", "TRANSFORM", "END"] as DefinitionNode["type"][]).map((type) => <button type="button" draggable="true" key={type} className="workflow-palette-item" onClick={() => addNode(type)} onDragStart={(event) => handlePaletteDragStart(event, type)}><span className="workflow-palette-dot" style={{ background: colors[type] }} /><span>{typeLabels[type]}</span><span className="workflow-palette-add">+</span></button>)}
      </aside>
      <div className={`workflow-canvas-wrap ${paletteDragActive ? "is-drop-target" : ""}`} onDragEnter={() => setPaletteDragActive(true)} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as globalThis.Node)) setPaletteDragActive(false); }} onDrop={handleCanvasDrop}>
        {paletteDragActive ? <div className="workflow-drop-hint" role="status">Drop to add node</div> : null}
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onInit={setFlowInstance} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => { setSelected(node.id); setInspectorOpen(true); }} fitView minZoom={0.25} maxZoom={1.8} proOptions={{ hideAttribution: true }}><Background gap={20} size={1} color="var(--grid-line)" /><MiniMap nodeColor={(node) => colors[(node.data as CanvasNodeData).type]} pannable zoomable nodeStrokeWidth={1} /><Controls /></ReactFlow>
      </div>
      <aside className={`workflow-inspector ${inspectorOpen ? "" : "is-collapsed"}`}>
        <div className="workflow-panel-heading"><span className="panel-label">Inspector</span><div className="workflow-panel-heading-actions"><small>{activeNode ? "Selected node" : "Nothing selected"}</small><button className="icon-button workflow-inspector-toggle" type="button" aria-label={inspectorOpen ? "Collapse inspector" : "Open inspector"} aria-expanded={inspectorOpen} onClick={() => setInspectorOpen((current) => !current)}>{inspectorOpen ? <PanelRightClose size={15} aria-hidden="true" /> : <PanelRightOpen size={15} aria-hidden="true" />}</button></div></div>
        {inspectorOpen ? <>{activeNode ? <><div className="workflow-inspector-heading"><span className="workflow-inspector-dot" style={{ background: colors[activeNode.data.type] }} /><div><strong>{activeNode.data.label}</strong><small>{typeLabels[activeNode.data.type]} node · key <code>{activeNode.id}</code></small></div></div><label className="form-label">Node name<input value={activeNode.data.label} onChange={(event) => updateNodeLabel(event.target.value)} /></label>{activeNode.data.type === "AGENT" ? renderAgentConfig() : null}{activeNode.data.type === "TOOL" ? renderToolConfig() : null}{activeNode.data.type === "CONDITION" ? renderConditionConfig() : null}{activeNode.data.type === "TRANSFORM" ? renderTransformConfig() : null}{activeNode.data.type === "APPROVAL" ? renderApprovalConfig() : null}{activeNode.data.type === "END" ? renderEndConfig() : null}{activeNode.data.type === "START" ? renderSimpleConfig() : null}<button className="workflow-advanced-toggle" type="button" aria-expanded={advancedOpen} onClick={() => setAdvancedOpen((current) => !current)}><Settings2 size={14} aria-hidden="true" />{advancedOpen ? "Hide configuration guide" : "Show configuration guide"}<span>{advancedOpen ? "⌃" : "⌄"}</span></button>{advancedOpen ? <div className="workflow-guided-config"><div className="workflow-guided-config-heading"><Info size={15} aria-hidden="true" /><div><strong>Guided configuration</strong><p>Choose values in the fields above. VibesFactory converts them into the safe JSON contract automatically.</p></div></div><div className="workflow-guided-config-list"><span>✓ Human-readable labels and descriptions</span><span>✓ No JSON syntax required</span><span>✓ Validation runs before publish</span></div></div> : null}</> : <div className="workflow-inspector-empty"><Braces size={20} aria-hidden="true" /><strong>Select a node to configure it</strong><p>Choose an Agent, Tool, Condition or Transform and configure it with guided fields.</p></div>}{validation ? <div className={`workflow-validation ${validation.valid ? "valid" : "invalid"}`}><div>{validation.valid ? <Check size={15} /> : <CircleAlert size={15} />} {validation.valid ? "Graph is valid" : `${validation.errors.length} validation issue(s)`}</div>{validation.errors.slice(0, 4).map((issue, index) => <button type="button" key={`${issue.code}-${index}`} onClick={() => { if (issue.node_key) { setSelected(issue.node_key); setInspectorOpen(true); } }}>{issue.node_key ? `${issue.node_key}: ` : ""}{issue.message}</button>)}</div> : null}</> : null}
      </aside>
    </div>
    {runInputOpen ? <div className="modal-backdrop" role="presentation"><section className="modal-dialog workflow-run-input-dialog" role="dialog" aria-modal="true" aria-labelledby="workflow-run-input-heading"><div className="modal-heading"><div><span className="eyebrow">Run workflow</span><h2 id="workflow-run-input-heading">Provide workflow input</h2><p className="panel-copy">These fields become the input object available to Start and Agent nodes.</p></div><button className="icon-button modal-close" type="button" onClick={() => setRunInputOpen(false)} aria-label="Close workflow input dialog"><X size={17} aria-hidden="true" /></button></div><form className="modal-form" onSubmit={(event) => { event.preventDefault(); void executeRun(); }}><div className="workflow-input-list">{runInputFields.map((field) => <div className="workflow-input-row" key={field.id}><label className="form-label"><span>Field name</span><input value={field.key} onChange={(event) => updateRunInputField(field.id, { key: event.target.value })} placeholder="topic" autoComplete="off" /></label><label className="form-label"><span>Value type</span><select value={field.type} onChange={(event) => updateRunInputField(field.id, { type: event.target.value as RunInputField["type"] })}><option value="text">Text</option><option value="number">Number</option><option value="boolean">True / false</option></select></label><label className="form-label workflow-input-value"><span>Value</span>{field.type === "boolean" ? <select value={field.value || "false"} onChange={(event) => updateRunInputField(field.id, { value: event.target.value })}><option value="true">True</option><option value="false">False</option></select> : <input type={field.type === "number" ? "number" : "text"} value={field.value} onChange={(event) => updateRunInputField(field.id, { value: event.target.value })} placeholder={field.type === "number" ? "42" : "Research workflow orchestration"} />}</label><button className="icon-button danger workflow-input-remove" type="button" onClick={() => removeRunInputField(field.id)} aria-label={`Remove ${field.key || "input"} field`}><Trash2 size={15} aria-hidden="true" /></button></div>)}</div><button className="text-button workflow-input-add" type="button" onClick={addRunInputField}><Plus size={14} aria-hidden="true" />Add input field</button><small className="workflow-helper">The UI converts these values into JSON before the run starts, so no JSON syntax is required.</small><div className="modal-actions"><button className="button subtle-button" type="button" onClick={() => setRunInputOpen(false)}>Cancel</button><button className="button primary-button" type="submit" disabled={busy}><Play size={15} aria-hidden="true" />Start run</button></div></form></section></div> : null}
  </div></ReactFlowProvider>;
}
