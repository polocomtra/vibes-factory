"use client";

import {
  ArrowLeft,
  BrainCircuit,
  BookOpen,
  Check,
  ChevronDown,
  Clipboard,
  Code2,
  GitBranch,
  Globe2,
  LoaderCircle,
  Network,
  Play,
  Save,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "../../../components/app-shell";
import { ModelSelect } from "../../../components/model-select";
import { apiFetch, readApiError } from "../../../lib/api";
import {
  fetchAgent,
  fetchDraft,
  fetchModels,
  fetchVersion,
  fetchVersions,
  type Agent,
  type AgentDraft,
  type AgentVersion,
  type AgentVersionSummary,
  type ModelDefinition,
} from "../../../lib/agents";
import { listMemoryStores, type MemoryStore, type MemoryType } from "../../../lib/memory";
import {
  fetchDraftTools,
  fetchTools,
  type DraftTool,
  type Tool,
} from "../../../lib/tools";
import {
  attachDraftKnowledge,
  detachDraftKnowledge,
  listDraftKnowledge,
  listKnowledgeBases,
  type KnowledgeBase,
  type KnowledgeBinding,
} from "../../../lib/knowledge";
import {
  attachDraftGuardrail,
  detachDraftGuardrail,
  fetchDraftGuardrails,
  fetchGuardrailVersions,
  fetchGuardrails,
  setDraftGuardrailsEnabled,
  type DraftGuardrails,
  type GuardrailPolicy,
  type GuardrailVersion,
  type GuardrailHook,
} from "../../../lib/guardrails";

function dateLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function initialDraft(): AgentDraft {
  return {
    agent_id: "",
    instructions: "",
    model: {
      provider: "",
      name: "",
      config: {},
      reasoning_options: {},
      provider_options: {},
    },
    runtime_config: {
      max_steps: 20,
      max_model_calls: 10,
      max_tool_calls: 10,
      max_child_runs: 5,
      max_agent_depth: 3,
      max_total_tokens: 100000,
      timeout_seconds: 120,
    },
    memory_config: {
      enabled: false,
      memory_store_id: null,
      retrieve: { top_k: 5 },
      write: { enabled: true, types: ["PROFILE", "SEMANTIC"] },
    },
    guardrails_enabled: true,
    updated_at: "",
  };
}

type ToolFilter = "ALL" | "BUILT_IN" | "HTTP" | "MCP";

function toolKind(tool: Tool) {
  if (tool.built_in)
    return {
      label: "Built-in",
      className: "built-in",
      icon: <Zap size={11} aria-hidden="true" />,
    };
  if (tool.type === "HTTP")
    return {
      label: "HTTPS",
      className: "https",
      icon: <Globe2 size={11} aria-hidden="true" />,
    };
  if (tool.type === "MCP")
    return {
      label: "MCP",
      className: "mcp",
      icon: <Network size={11} aria-hidden="true" />,
    };
  return {
    label: "Workspace",
    className: "workspace",
    icon: <Zap size={11} aria-hidden="true" />,
  };
}

export default function AgentDetailPage() {
  const params = useParams<{ agentId: string }>();
  const router = useRouter();
  const agentId = params.agentId;
  const [agent, setAgent] = useState<Agent | null>(null);
  const [draft, setDraft] = useState<AgentDraft>(initialDraft);
  const [models, setModels] = useState<ModelDefinition[]>([]);
  const [versions, setVersions] = useState<AgentVersionSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<AgentVersion | null>(
    null,
  );
  const [tab, setTab] = useState<"configuration" | "versions" | "tools" | "knowledge" | "guardrails">(
    "configuration",
  );
  const [draftTools, setDraftTools] = useState<DraftTool[]>([]);
  const [pendingToolVersionIds, setPendingToolVersionIds] = useState<
    Set<string>
  >(new Set());
  const [catalogTools, setCatalogTools] = useState<Tool[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [knowledgeBindings, setKnowledgeBindings] = useState<KnowledgeBinding[]>([]);
  const [memoryStores, setMemoryStores] = useState<MemoryStore[]>([]);
  const [draftGuardrails, setDraftGuardrails] = useState<DraftGuardrails | null>(null);
  const [guardrailPolicies, setGuardrailPolicies] = useState<GuardrailPolicy[]>([]);
  const [guardrailVersions, setGuardrailVersions] = useState<Record<string, GuardrailVersion[]>>({});
  const [toolFilter, setToolFilter] = useState<ToolFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"save" | "publish" | "metadata" | null>(
    null,
  );
  const [dirty, setDirty] = useState(false);
  const [changeNote, setChangeNote] = useState("");
  const [runtimeOpen, setRuntimeOpen] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const agentData = await fetchAgent(agentId);
      const [draftData, modelData, versionData, draftToolData, draftKnowledgeData, memoryStoreData, guardrailData, policyData] =
        await Promise.all([
          fetchDraft(agentId),
          fetchModels(),
          fetchVersions(agentId),
          fetchDraftTools(agentId),
          listDraftKnowledge(agentId),
          listMemoryStores(agentData.workspace_id),
          fetchDraftGuardrails(agentId),
          fetchGuardrails(agentData.workspace_id),
        ]);
      const catalogToolData = await fetchTools(agentData.workspace_id);
      const knowledgeData = await listKnowledgeBases(
        agentData.workspace_id,
        undefined,
        "ACTIVE",
      );
      const versionEntries = await Promise.all(
        policyData.map(async (policy) => [policy.id, await fetchGuardrailVersions(policy.id)] as const),
      );
      setAgent(agentData);
      setName(agentData.name);
      setDescription(agentData.description ?? "");
      setDraft(draftData);
      setModels(modelData);
      setVersions(versionData);
      setDraftTools(draftToolData);
      setPendingToolVersionIds(
        new Set(
          draftToolData
            .filter((item) => item.enabled)
            .map((item) => item.tool_version_id),
        ),
      );
      setCatalogTools(catalogToolData);
      setKnowledgeBindings(draftKnowledgeData.data);
      setMemoryStores(memoryStoreData.data);
      setKnowledgeBases(knowledgeData.data);
      setDraftGuardrails(guardrailData);
      setGuardrailPolicies(policyData);
      setGuardrailVersions(Object.fromEntries(versionEntries));
      setSelectedVersion(null);
      setDirty(false);
    } catch (reason: unknown) {
      setError(
        reason instanceof Error ? reason.message : "Unable to load agent.",
      );
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  async function toggleGuardrails(enabled: boolean) {
    setError(null);
    try {
      setDraftGuardrails(await setDraftGuardrailsEnabled(agentId, enabled));
      setMessage(enabled ? "Guardrails enabled for future versions." : "Guardrails disabled for future versions.");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to update guardrails.");
    }
  }

  async function toggleGuardrailBinding(version: GuardrailVersion, hook: GuardrailHook, shouldAttach: boolean) {
    if (!draftGuardrails) return;
    setError(null);
    try {
      if (shouldAttach) await attachDraftGuardrail(agentId, version.id, hook);
      else await detachDraftGuardrail(agentId, version.id, hook);
      setDraftGuardrails(await fetchDraftGuardrails(agentId));
      setMessage(shouldAttach ? "Guardrail attached to the draft." : "Guardrail detached from the draft.");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to update guardrail binding.");
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!publishOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setPublishOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [publishOpen]);

  function updateDraft(next: AgentDraft) {
    setDraft(next);
    setDirty(true);
    setMessage(null);
  }

  async function saveDraft() {
    setBusy("save");
    setError(null);
    setMessage(null);
    if (draft.memory_config.enabled && !draft.memory_config.memory_store_id) {
      setError("Choose a memory store before enabling long-term memory.");
      setBusy(null);
      return;
    }
    const model =
      draft.model.provider === "azure_openai"
        ? {
            ...draft.model,
            config: {
              max_output_tokens: draft.model.config.max_output_tokens ?? 4096,
            },
          }
        : draft.model;
    try {
      const response = await apiFetch(`/v1/agents/${agentId}/draft`, {
        method: "PATCH",
        body: JSON.stringify({
          instructions: draft.instructions,
          model,
          runtime_config: draft.runtime_config,
          memory_config: draft.memory_config,
        }),
      });
      if (!response.ok) throw new Error(await readApiError(response));
      const additions = catalogTools.flatMap((tool) => {
        const version = tool.versions[0];
        return version &&
          pendingToolVersionIds.has(version.id) &&
          !draftTools.some((item) => item.tool_version_id === version.id)
          ? [version.id]
          : [];
      });
      const removals = draftTools
        .filter(
          (item) =>
            item.enabled && !pendingToolVersionIds.has(item.tool_version_id),
        )
        .map((item) => item.tool_version_id);
      const bindingResponses = await Promise.all([
        ...additions.map((toolVersionId) =>
          apiFetch(`/v1/agents/${agentId}/draft/tools`, {
            method: "POST",
            body: JSON.stringify({ tool_version_id: toolVersionId }),
          }),
        ),
        ...removals.map((toolVersionId) =>
          apiFetch(`/v1/agents/${agentId}/draft/tools/${toolVersionId}`, {
            method: "DELETE",
          }),
        ),
      ]);
      const failedBinding = bindingResponses.find(
        (bindingResponse) => !bindingResponse.ok,
      );
      if (failedBinding) throw new Error(await readApiError(failedBinding));
      setDraft((await response.json()) as AgentDraft);
      setMessage(
        additions.length + removals.length > 0
          ? "Draft and tool bindings saved."
          : "Draft saved.",
      );
      await load();
    } catch (reason: unknown) {
      setError(
        reason instanceof Error ? reason.message : "Unable to save draft.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function saveMetadata() {
    setBusy("metadata");
    setError(null);
    setMessage(null);
    const response = await apiFetch(`/v1/agents/${agentId}`, {
      method: "PATCH",
      body: JSON.stringify({ name, description: description || null }),
    });
    if (!response.ok) {
      setError(await readApiError(response));
      setBusy(null);
      return;
    }
    setAgent((await response.json()) as Agent);
    setMessage("Agent details saved.");
    setBusy(null);
  }

  async function publish() {
    setBusy("publish");
    setError(null);
    setMessage(null);
    const response = await apiFetch(`/v1/agents/${agentId}/versions`, {
      method: "POST",
      body: JSON.stringify({ change_note: changeNote || null }),
    });
    if (!response.ok) {
      setError(await readApiError(response));
      setBusy(null);
      return;
    }
    setChangeNote("");
    setMessage("Version published.");
    setBusy(null);
    await load();
    setTab("versions");
  }

  async function selectVersion(version: AgentVersionSummary) {
    setError(null);
    try {
      setSelectedVersion(await fetchVersion(agentId, version.id));
    } catch (reason: unknown) {
      setError(
        reason instanceof Error ? reason.message : "Unable to load version.",
      );
    }
  }

  function toggleTool(toolVersionId: string, enabled: boolean) {
    setPendingToolVersionIds((current) => {
      const next = new Set(current);
      if (enabled) next.add(toolVersionId);
      else next.delete(toolVersionId);
      return next;
    });
    setDirty(true);
    setMessage(null);
    setError(null);
  }

  async function toggleKnowledge(base: KnowledgeBase, enabled: boolean) {
    setError(null);
    try {
      if (enabled) {
        const binding = await attachDraftKnowledge(agentId, base.id);
        setKnowledgeBindings((current) => [...current.filter((item) => item.knowledge_base_id !== base.id), binding]);
      } else {
        await detachDraftKnowledge(agentId, base.id);
        setKnowledgeBindings((current) => current.filter((item) => item.knowledge_base_id !== base.id));
      }
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to update knowledge binding.");
    }
  }

  function updateRuntime(
    key: keyof AgentDraft["runtime_config"],
    value: string,
  ) {
    updateDraft({
      ...draft,
      runtime_config: { ...draft.runtime_config, [key]: Number(value) },
    });
  }

  useEffect(() => {
    if (tab !== "versions" || selectedVersion || versions.length === 0) return;
    let cancelled = false;
    setError(null);
    void fetchVersion(agentId, versions[0].id)
      .then((version) => {
        if (!cancelled) setSelectedVersion(version);
      })
      .catch((reason: unknown) => {
        if (!cancelled)
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to load version.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, tab, versions, selectedVersion]);

  const toolBindingsDirty =
    draftTools
      .filter((item) => item.enabled)
      .some(
        (item) => pendingToolVersionIds.has(item.tool_version_id) === false,
      ) ||
    catalogTools.some((tool) => {
      const version = tool.versions[0];
      return Boolean(
        version &&
        pendingToolVersionIds.has(version.id) &&
        !draftTools.some((item) => item.tool_version_id === version.id),
      );
    });

  const visibleCatalogTools = catalogTools.filter((tool) => {
    if (toolFilter === "ALL") return true;
    if (toolFilter === "BUILT_IN") return tool.built_in;
    if (toolFilter === "HTTP") return !tool.built_in && tool.type === "HTTP";
    return tool.type === "MCP";
  });

  const toolFilterOptions: Array<[ToolFilter, string, number]> = [
    ["ALL", "All", catalogTools.length],
    [
      "BUILT_IN",
      "Built-in",
      catalogTools.filter((tool) => tool.built_in).length,
    ],
    [
      "HTTP",
      "HTTPS",
      catalogTools.filter((tool) => !tool.built_in && tool.type === "HTTP")
        .length,
    ],
    ["MCP", "MCP", catalogTools.filter((tool) => tool.type === "MCP").length],
  ];

  if (loading)
    return (
      <AppShell>
        <section className="panel agent-state">
          <LoaderCircle className="spin" size={18} aria-hidden="true" />
          Loading agent…
        </section>
      </AppShell>
    );
  if (!agent)
    return (
      <AppShell>
        <section className="panel agent-empty-state">
          <h2>Agent unavailable</h2>
          <p className="panel-copy">
            {error || "This agent could not be found."}
          </p>
          <button
            className="button secondary-button"
            type="button"
            onClick={() => router.push("/agents")}
          >
            Back to agents
          </button>
        </section>
      </AppShell>
    );

  return (
    <AppShell>
      <div className="page-header agent-detail-header">
        <div>
          <button
            className="text-button"
            type="button"
            onClick={() => router.push("/agents")}
          >
            <ArrowLeft size={14} aria-hidden="true" />
            Back to agents
          </button>
          <p className="eyebrow agent-eyebrow">
            VibesFactory / Agent control plane
          </p>
          <div className="agent-title-row">
            <span className="agent-avatar large">
              <BotIcon />
            </span>
            <div>
              <h1>{agent.name}</h1>
              <p className="page-description">
                <code>{agent.slug}</code> ·{" "}
                {agent.status === "ACTIVE" ? "Active" : "Archived"}
              </p>
            </div>
          </div>
        </div>
        <div className="header-controls agent-command-bar">
          <span
            className={`status-badge ${agent.status === "ACTIVE" ? "success" : "muted"}`}
          >
            <span />
            {agent.latest_version_number
              ? `v${agent.latest_version_number} published`
              : "Draft only"}
          </span>
          <button
            className="button secondary-button command-button"
            type="button"
            onClick={() => router.push(`/agents/${agentId}/playground`)}
            disabled={agent.latest_version_number === 0}
          >
            <Play size={15} aria-hidden="true" />
            Open playground
          </button>
          <button
            className="button secondary-button command-button"
            type="button"
            onClick={() => void saveDraft()}
            disabled={!dirty || busy !== null}
            aria-label="Save agent draft"
          >
            {busy === "save" ? (
              <LoaderCircle className="spin" size={15} aria-hidden="true" />
            ) : (
              <Save size={15} aria-hidden="true" />
            )}
            Save draft
          </button>
          <button
            className="button primary-button command-button"
            type="button"
            onClick={() => setPublishOpen(true)}
            disabled={busy !== null || dirty || agent.status === "ARCHIVED"}
            title={dirty ? "Save the draft before publishing." : undefined}
          >
            <GitBranch size={15} aria-hidden="true" />
            Publish agent
          </button>
        </div>
      </div>
      <section className="agent-detail-tabs" role="tablist">
        <button
          className={
            tab === "configuration" ? "settings-tab active" : "settings-tab"
          }
          type="button"
          role="tab"
          aria-selected={tab === "configuration"}
          onClick={() => setTab("configuration")}
        >
          <Code2 size={15} aria-hidden="true" />
          Configuration{dirty ? <span className="tab-count">*</span> : null}
        </button>
        <button
          className={tab === "knowledge" ? "settings-tab active" : "settings-tab"}
          type="button"
          role="tab"
          aria-selected={tab === "knowledge"}
          onClick={() => setTab("knowledge")}
        >
          <BookOpen size={15} aria-hidden="true" />
          Knowledge<span className="tab-count">{knowledgeBindings.length}</span>
        </button>
        <button
          className={tab === "tools" ? "settings-tab active" : "settings-tab"}
          type="button"
          role="tab"
          aria-selected={tab === "tools"}
          onClick={() => setTab("tools")}
        >
          <Zap size={15} aria-hidden="true" />
          Tools<span className="tab-count">{pendingToolVersionIds.size}</span>
        </button>
        <button
          className={tab === "guardrails" ? "settings-tab active" : "settings-tab"}
          type="button"
          role="tab"
          aria-selected={tab === "guardrails"}
          onClick={() => setTab("guardrails")}
        >
          <ShieldCheck size={15} aria-hidden="true" />
          Guardrails<span className="tab-count">{draftGuardrails?.bindings.length ?? 0}</span>
        </button>
        <button
          className={
            tab === "versions" ? "settings-tab active" : "settings-tab"
          }
          type="button"
          role="tab"
          aria-selected={tab === "versions"}
          onClick={() => setTab("versions")}
        >
          <GitBranch size={15} aria-hidden="true" />
          Versions<span className="tab-count">{versions.length}</span>
        </button>
      </section>
      {error ? (
        <div className="form-error agent-alert agent-detail-alert" role="alert">
          {error}
        </div>
      ) : null}
      {message ? (
        <div
          className="form-success agent-alert agent-detail-alert"
          role="status"
        >
          <Check size={14} aria-hidden="true" />
          {message}
        </div>
      ) : null}
      {tab === "guardrails" ? (
        <section className="panel agent-tools-panel agent-guardrails-panel">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">Execution boundaries</span>
              <h2>Guardrails for this draft</h2>
            </div>
            <div className="agent-tools-heading-actions guardrail-heading-actions">
              <span className={`tool-binding-state ${draftGuardrails?.enabled ? "saved" : "unsaved"}`}>
                {draftGuardrails?.enabled ? "Enabled next publish" : "Disabled next publish"}
              </span>
              <label className="guardrail-header-toggle">
                <span className="sr-only">Enable guardrails for future published versions</span>
                <input
                  type="checkbox"
                  role="switch"
                  checked={draftGuardrails?.enabled ?? true}
                  onChange={(event) => void toggleGuardrails(event.target.checked)}
                  aria-describedby="guardrails-master-help"
                />
                <span className="toggle-control" aria-hidden="true"><span /></span>
              </label>
            </div>
          </div>
          <p className="panel-copy agent-tools-copy" id="guardrails-master-help">
            Toggle protection locally, then publish a new immutable agent version. Existing versions are unchanged.
          </p>
          {!draftGuardrails?.enabled ? (
            <div className="form-warning guardrails-disabled-warning" role="status">
              Guardrails are disabled for the next version. Authentication, authorization, budgets, schema validation, and credential redaction remain active.
            </div>
          ) : null}
          <div className="agent-guardrails-section">
            <div className="agent-guardrails-section-heading">
              <div>
                <span className="panel-kicker">Platform default · v1</span>
                <h3>Balanced protection</h3>
              </div>
              <ShieldCheck size={18} aria-hidden="true" />
            </div>
            <article className="agent-guardrail-row agent-guardrail-baseline-row">
              <span className="tool-card-icon agent-guardrail-icon"><ShieldCheck size={16} aria-hidden="true" /></span>
              <span className="agent-tool-copy">
                <strong>Platform baseline</strong>
                <small>Redacts secrets and PII, limits payload size, and blocks high-risk side-effect tools.</small>
              </span>
              <span className={`status-badge ${draftGuardrails?.enabled ? "success" : "muted"}`}><span />{draftGuardrails?.enabled ? "Included" : "Disabled"}</span>
            </article>
            <div className="agent-guardrail-tags" aria-label="Platform baseline protections">
              <span>Secrets + PII</span>
              <span>Payload limits</span>
              <span>High-risk tools</span>
            </div>
          </div>
          <div className="agent-guardrails-section agent-guardrails-custom-section">
            <div className="agent-guardrails-section-heading">
              <div>
                <span className="panel-kicker">Workspace policies</span>
                <h3>Custom guardrails</h3>
              </div>
              <span className="code-hint">{guardrailPolicies.length} POLICIES</span>
            </div>
            <div className="agent-guardrail-list">
              {guardrailPolicies.length === 0 ? <div className="agent-tools-filter-empty">No custom policies yet. Create one from the Guardrails workspace page.</div> : guardrailPolicies.map((policy) => (guardrailVersions[policy.id] ?? []).slice(0, 1).map((version) => (
                <article className="agent-guardrail-row" key={version.id}>
                  <span className="tool-card-icon agent-guardrail-icon"><ShieldCheck size={16} aria-hidden="true" /></span>
                  <span className="agent-tool-copy">
                    <strong>{policy.name} · v{version.version_number}</strong>
                    <small>{policy.description || "Versioned workspace policy"}</small>
                  </span>
                  <div className="guardrail-hook-actions">{(["INPUT", "MODEL_OUTPUT", "TOOL_INPUT", "TOOL_OUTPUT"] as GuardrailHook[]).map((hook) => { const binding = draftGuardrails?.bindings.find((item) => item.guardrail_version_id === version.id && item.hook === hook); return <label key={hook} className={`guardrail-hook-toggle ${binding ? "active" : ""}`}><input type="checkbox" checked={Boolean(binding)} onChange={(event) => void toggleGuardrailBinding(version, hook, event.target.checked)} aria-label={`${binding ? "Detach" : "Attach"} ${policy.name} ${hook}`} /><span>{hook.replace("_", " ")}</span></label>; })}</div>
                </article>
              ))) }
            </div>
          </div>
        </section>
      ) : tab === "knowledge" ? (
        <section className="panel agent-tools-panel">
          <div className="panel-heading"><div><span className="panel-kicker">Grounded context</span><h2>Knowledge bases for this draft</h2></div><BookOpen size={18} aria-hidden="true" /></div>
          <p className="panel-copy agent-tools-copy">Bindings are snapshotted when you publish. Choose top-k sources per base; advanced filters remain optional.</p>
          <div className="agent-tool-list">
            {knowledgeBases.length === 0 ? <div className="agent-tools-filter-empty">No knowledge bases available. Create one from Knowledge.</div> : knowledgeBases.map((base) => { const enabled = knowledgeBindings.some((binding) => binding.knowledge_base_id === base.id); return <label className="agent-tool-row agent-tool-switch-row" key={base.id}><span className="tool-card-icon"><BookOpen size={16} aria-hidden="true" /></span><span className="agent-tool-copy"><strong>{base.name}</strong><small>{base.ready_document_count} ready documents · {base.embedding_model}</small></span><span className={`status-badge ${base.status === "ACTIVE" ? "success" : "muted"}`}><span />{base.status}</span><span className="tool-switch-status"><span>{enabled ? "Attached" : "Detached"}</span><span className="tool-switch"><input type="checkbox" checked={enabled} disabled={base.status !== "ACTIVE"} onChange={(event) => void toggleKnowledge(base, event.target.checked)} aria-label={`${enabled ? "Detach" : "Attach"} ${base.name}`} /><span className="tool-switch-track" aria-hidden="true"><span /></span></span></span></label>; })}
          </div>
        </section>
      ) : tab === "tools" ? (
        <section className="panel agent-tools-panel">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">Capability bindings</span>
              <h2>Tools for this draft</h2>
            </div>
            <div className="agent-tools-heading-actions">
              <span
                className={
                  "tool-binding-state " +
                  (toolBindingsDirty ? "unsaved" : "saved")
                }
              >
                {toolBindingsDirty ? "Unsaved changes" : "Synced"}
              </span>
              <button
                className="button primary-button"
                type="button"
                onClick={() => void saveDraft()}
                disabled={!toolBindingsDirty || busy !== null}
              >
                {busy === "save" ? (
                  <LoaderCircle className="spin" size={14} aria-hidden="true" />
                ) : (
                  <Save size={14} aria-hidden="true" />
                )}
                Save tool changes
              </button>
            </div>
          </div>
          <p className="panel-copy agent-tools-copy">
            Toggle capabilities locally, then save the complete set in one
            batch. Enabled tools become runtime-available only after publishing
            a new agent version.
          </p>
          <div
            className="agent-tool-filters"
            role="group"
            aria-label="Filter tools by type"
          >
            {toolFilterOptions.map(([value, label, count]) => (
              <button
                className={toolFilter === value ? "selected" : undefined}
                key={value}
                type="button"
                aria-pressed={toolFilter === value}
                onClick={() => setToolFilter(value)}
              >
                {label}
                <span>{count}</span>
              </button>
            ))}
          </div>
          <div className="agent-tool-list">
            {visibleCatalogTools.length === 0 ? (
              <div className="agent-tools-filter-empty">
                No tools match this filter.
              </div>
            ) : null}
            {visibleCatalogTools.map((tool) => {
              const version = tool.versions[0];
              const enabled = Boolean(
                version && pendingToolVersionIds.has(version.id),
              );
              const kind = toolKind(tool);
              return version ? (
                <label
                  className="agent-tool-row agent-tool-switch-row"
                  key={version.id}
                >
                  <span className="tool-card-icon">
                    <Zap size={16} aria-hidden="true" />
                  </span>
                  <span className="agent-tool-copy">
                    <strong>{tool.name}</strong>
                    <small>
                      {tool.description} · v{version.version_number}
                    </small>
                  </span>
                  <span className={`agent-tool-kind ${kind.className}`}>
                    {kind.icon}
                    {kind.label}
                  </span>
                  <span className="tool-switch-status">
                    <span>{enabled ? "Enabled" : "Disabled"}</span>
                    <span className="tool-switch">
                      <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(event) =>
                          toggleTool(version.id, event.target.checked)
                        }
                        aria-label={
                          enabled
                            ? "Disable " + tool.name
                            : "Enable " + tool.name
                        }
                      />
                      <span className="tool-switch-track" aria-hidden="true">
                        <span />
                      </span>
                    </span>
                  </span>
                </label>
              ) : null;
            })}
          </div>
        </section>
      ) : tab === "configuration" ? (
        <main className="agent-detail-layout">
          <section className="panel agent-form-panel">
            <div className="panel-heading">
              <div>
                <span className="panel-kicker">Identity</span>
                <h2>Agent details</h2>
              </div>
              <ShieldCheck size={18} aria-hidden="true" />
            </div>
            <div className="field-grid">
              <label>
                Name
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label>
                Slug
                <input value={agent.slug} disabled />
              </label>
            </div>
            <label>
              Description
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={3}
              />
            </label>
            <div className="panel-inline-actions">
              <span className="field-helper">
                Metadata changes do not create a new version.
              </span>
              <button
                className="button secondary-button"
                type="button"
                onClick={() => void saveMetadata()}
                disabled={busy !== null}
              >
                {busy === "metadata" ? (
                  <LoaderCircle className="spin" size={14} aria-hidden="true" />
                ) : (
                  <Save size={14} aria-hidden="true" />
                )}
                Save details
              </button>
            </div>
          </section>
          <section className="panel agent-form-panel">
            <div className="panel-heading">
              <div>
                <span className="panel-kicker">Behavior</span>
                <h2>Instructions</h2>
              </div>
            </div>
            <textarea
              className="instructions-editor"
              value={draft.instructions}
              onChange={(event) =>
                updateDraft({ ...draft, instructions: event.target.value })
              }
              rows={14}
            />
          </section>
          <section className="panel agent-form-panel">
            <div className="panel-heading">
              <div>
                <span className="panel-kicker">Model</span>
                <h2>Model configuration</h2>
              </div>
            </div>
            <div className="field-grid">
              <label>
                Model
                <ModelSelect
                  models={models}
                  value={`${draft.model.provider}:${draft.model.name}`}
                  onChange={(value) => {
                    const model = models.find(
                      (item) => `${item.provider}:${item.name}` === value,
                    );
                    if (model) {
                      const config = { ...draft.model.config };
                      if (model.provider === "azure_openai")
                        delete config.temperature;
                      updateDraft({
                        ...draft,
                        model: {
                          ...draft.model,
                          provider: model.provider,
                          name: model.name,
                          config,
                        },
                      });
                    }
                  }}
                />
              </label>
              <label htmlFor="agent-temperature">
                <span>Temperature</span>
                <input
                  id="agent-temperature"
                  type="number"
                  inputMode="decimal"
                  min="0"
                  max="2"
                  step="0.1"
                  value={String(draft.model.config.temperature ?? 0.2)}
                  disabled={draft.model.provider === "azure_openai"}
                  aria-describedby="agent-temperature-helper"
                  onChange={(event) =>
                    updateDraft({
                      ...draft,
                      model: {
                        ...draft.model,
                        config: {
                          ...draft.model.config,
                          temperature: Number(event.target.value),
                        },
                      },
                    })
                  }
                />
                <small id="agent-temperature-helper">
                  {draft.model.provider === "azure_openai"
                    ? "Temporarily disabled for Azure OpenAI reasoning models."
                    : "Lower values make responses more consistent."}
                </small>
              </label>
              <label>
                Max output tokens
                <input
                  type="number"
                  min="1"
                  value={String(draft.model.config.max_output_tokens ?? 4096)}
                  onChange={(event) =>
                    updateDraft({
                      ...draft,
                      model: {
                        ...draft.model,
                        config: {
                          ...draft.model.config,
                          max_output_tokens: Number(event.target.value),
                        },
                      },
                    })
                  }
                />
              </label>
            </div>
          </section>
          <section className="panel agent-form-panel runtime-panel">
            <button
              className="runtime-accordion-trigger"
              type="button"
              aria-expanded={runtimeOpen}
              aria-controls="runtime-config-content"
              onClick={() => setRuntimeOpen((open) => !open)}
            >
              <span>
                <span className="panel-kicker">Execution</span>
                <strong>Runtime configuration</strong>
                <small>
                  Limits for steps, model calls, tools and timeouts.
                </small>
              </span>
              <span className="runtime-accordion-meta">
                <span className="code-hint">V1</span>
                <ChevronDown
                  className={
                    runtimeOpen ? "accordion-chevron open" : "accordion-chevron"
                  }
                  size={18}
                  aria-hidden="true"
                />
              </span>
            </button>
            {runtimeOpen ? (
              <div className="runtime-grid" id="runtime-config-content">
                {(
                  [
                    "max_steps",
                    "max_model_calls",
                    "max_tool_calls",
                    "max_child_runs",
                    "max_agent_depth",
                    "max_total_tokens",
                    "timeout_seconds",
                  ] as const
                ).map((key) => (
                  <label key={key}>
                    {key.replaceAll("_", " ")}
                    <input
                      type="number"
                      min="0"
                      value={String(draft.runtime_config[key])}
                      onChange={(event) =>
                        updateRuntime(key, event.target.value)
                      }
                    />
                  </label>
                ))}
              </div>
            ) : null}
          </section>
          <section className="panel agent-form-panel">
            <div className="panel-heading">
              <div>
                <span className="panel-kicker">Memory</span>
                <h2>Long-term memory</h2>
              </div>
              <span className={`status-badge ${draft.memory_config.enabled ? "success" : "muted"}`}><span />{draft.memory_config.enabled ? "Enabled" : "Disabled"}</span>
            </div>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={draft.memory_config.enabled}
                onChange={(event) =>
                  updateDraft({
                    ...draft,
                    memory_config: {
                      ...draft.memory_config,
                      enabled: event.target.checked,
                    },
                  })
                }
              />
              <span className="toggle-control" aria-hidden="true">
                <span />
              </span>
              <span className="toggle-copy">
                <strong>Enable long-term memory</strong>
                <small>
                  Store durable user facts separately from session history. Memory content is reference data, not instructions.
                </small>
              </span>
            </label>
            {draft.memory_config.enabled ? <div className="memory-config-grid">
              <label>Memory store<select value={draft.memory_config.memory_store_id ?? ""} onChange={(event) => updateDraft({ ...draft, memory_config: { ...draft.memory_config, memory_store_id: event.target.value || null } })}><option value="">Select a memory store</option>{memoryStores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select><small>{memoryStores.length ? "Published versions keep this binding immutable." : "Create a store from the Memory page first."}</small></label>
              <label>Retrieve top-k<input type="number" min="1" max="20" value={draft.memory_config.retrieve.top_k} onChange={(event) => updateDraft({ ...draft, memory_config: { ...draft.memory_config, retrieve: { top_k: Number(event.target.value) || 1 } } })} /><small>How many relevant memories enter each run.</small></label>
              <label className="toggle-row memory-write-toggle"><input type="checkbox" checked={draft.memory_config.write.enabled} onChange={(event) => updateDraft({ ...draft, memory_config: { ...draft.memory_config, write: { ...draft.memory_config.write, enabled: event.target.checked } } })} /><span className="toggle-control" aria-hidden="true"><span /></span><span className="toggle-copy"><strong>Extract after successful runs</strong><small>Candidate extraction runs asynchronously and never blocks chat.</small></span></label>
              <fieldset className="memory-types-fieldset"><legend>Memory types to extract</legend><div className="memory-type-options">{(["PROFILE", "SEMANTIC", "SUMMARY", "PROCEDURAL"] as MemoryType[]).map((memoryType) => <label className="toggle-row memory-type-switch" key={memoryType}><input type="checkbox" role="switch" aria-label={`Extract ${memoryType.toLowerCase()} memories`} checked={draft.memory_config.write.types.includes(memoryType)} onChange={(event) => { const types = event.target.checked ? [...draft.memory_config.write.types, memoryType] : draft.memory_config.write.types.filter((item) => item !== memoryType); updateDraft({ ...draft, memory_config: { ...draft.memory_config, write: { ...draft.memory_config.write, types: types.length ? types : ["PROFILE"] } } }); }} /><span className="toggle-control" aria-hidden="true"><span /></span><span className="toggle-copy"><strong>{memoryType}</strong></span></label>)}</div></fieldset>
            </div> : null}
            <button className="text-button memory-browser-link" type="button" onClick={() => router.push("/memory")}><BrainCircuit size={14} aria-hidden="true" />Open memory browser</button>
          </section>
        </main>
      ) : (
        <div className="versions-layout">
          <section className="panel versions-list-panel">
            <div className="panel-heading">
              <div>
                <span className="panel-kicker">Immutable history</span>
                <h2>Published versions</h2>
              </div>
              <span className="code-hint">{versions.length} TOTAL</span>
            </div>
            {versions.length === 0 ? (
              <div className="agent-state">
                <GitBranch size={18} aria-hidden="true" />
                No versions published yet.
              </div>
            ) : (
              <div className="version-list">
                {versions.map((version) => (
                  <button
                    className={
                      selectedVersion?.id === version.id
                        ? "version-row selected"
                        : "version-row"
                    }
                    type="button"
                    key={version.id}
                    onClick={() => void selectVersion(version)}
                  >
                    <span className="version-number">
                      v{version.version_number}
                    </span>
                    <span>
                      <strong>
                        {version.change_note || "Configuration snapshot"}
                      </strong>
                      <small>{dateLabel(version.created_at)}</small>
                    </span>
                    <span>→</span>
                  </button>
                ))}
              </div>
            )}
          </section>
          <section className="panel version-inspector">
            {selectedVersion ? (
              <>
                <div className="panel-heading">
                  <div>
                    <span className="panel-kicker">Read-only snapshot</span>
                    <h2>Version {selectedVersion.version_number}</h2>
                  </div>
                  <span className="status-badge success">
                    <span />
                    Immutable
                  </span>
                </div>
                <div className="snapshot-meta">
                  <span>
                    Model <b>{selectedVersion.model.name}</b>
                  </span>
                  <span>
                    Provider <b>{selectedVersion.model.provider}</b>
                  </span>
                  <span>
                    Published <b>{dateLabel(selectedVersion.created_at)}</b>
                  </span>
                </div>
                <h3>Instructions</h3>
                <pre>{selectedVersion.instructions}</pre>
                <h3>Runtime snapshot</h3>
                <pre>{JSON.stringify(selectedVersion.snapshot, null, 2)}</pre>
                <button
                  className="button secondary-button"
                  type="button"
                  onClick={() =>
                    navigator.clipboard?.writeText(
                      JSON.stringify(selectedVersion.snapshot, null, 2),
                    )
                  }
                >
                  <Clipboard size={14} aria-hidden="true" />
                  Copy snapshot
                </button>
              </>
            ) : (
              <div className="agent-empty-state compact">
                <GitBranch size={24} aria-hidden="true" />
                <h2>Select a version</h2>
                <p className="panel-copy">
                  Inspect the immutable instructions, model and runtime
                  snapshot.
                </p>
              </div>
            )}
          </section>
        </div>
      )}
      {publishOpen ? (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setPublishOpen(false);
          }}
        >
          <section
            className="modal-dialog publish-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="publish-dialog-title"
            aria-describedby="publish-dialog-copy"
          >
            <div className="modal-heading">
              <div>
                <span className="panel-kicker">Release</span>
                <h2 id="publish-dialog-title">Publish agent</h2>
                <p id="publish-dialog-copy" className="panel-copy">
                  Create an immutable runtime snapshot from the saved draft.
                </p>
              </div>
              <button
                className="icon-button modal-close"
                type="button"
                aria-label="Close publish dialog"
                onClick={() => setPublishOpen(false)}
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <div className="publish-summary">
              <span>
                <strong>Target version</strong>
                <b>v{agent.latest_version_number + 1}</b>
              </span>
              <span>
                <strong>Last saved</strong>
                <b>
                  {draft.updated_at
                    ? dateLabel(draft.updated_at)
                    : "Not saved yet"}
                </b>
              </span>
              <span>
                <strong>Guardrails</strong>
                <b>{draftGuardrails?.enabled ? "Protected" : "Disabled"}</b>
              </span>
            </div>
            {!draftGuardrails?.enabled ? (
              <div className="form-warning memory-publish-warning" role="status">
                This version will publish without Phase 11 guardrails. Core platform security remains active.
              </div>
            ) : null}
            {draft.memory_config.enabled ? (
              <div className="field-helper memory-publish-warning" role="status">
                Memory retrieval and asynchronous extraction will be frozen into
                this published version. Future memory configuration changes
                require another publish.
              </div>
            ) : null}
            <label className="publish-note-field">
              Change note{" "}
              <textarea
                value={changeNote}
                onChange={(event) => setChangeNote(event.target.value)}
                rows={3}
                placeholder="Describe what changed (optional)"
              />
            </label>
            <p className="field-helper">
              Publishing freezes the current draft. Save any pending edits
              before publishing.
            </p>
            <div className="modal-actions">
              <button
                className="button secondary-button"
                type="button"
                onClick={() => setPublishOpen(false)}
              >
                Cancel
              </button>
              <button
                className="button primary-button"
                type="button"
                onClick={() => {
                  setPublishOpen(false);
                  void publish();
                }}
                disabled={busy !== null}
              >
                <Sparkles size={15} aria-hidden="true" />
                Publish version
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </AppShell>
  );
}

function BotIcon() {
  return <BotGlyph />;
}
function BotGlyph() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden="true"
    >
      <rect x="4" y="6" width="16" height="13" rx="3" />
      <path d="M12 3v3M8 12h.01M16 12h.01M8 16h8" />
    </svg>
  );
}
