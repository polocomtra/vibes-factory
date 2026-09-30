"use client";

import { ArrowLeft, Check, CheckCircle2, CircleAlert, Clock3, FlaskConical, LoaderCircle, Plus, RefreshCw, Scale, X } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "../../../components/app-shell";
import { PrimarySelect } from "../../../components/primary-select";
import { PrimaryTextArea, PrimaryTextInput } from "../../../components/primary-text-field";
import { apiFetch, readApiError } from "../../../lib/api";
import { fetchAgents, fetchModels, fetchVersions, type Agent, type AgentVersionSummary, type ModelDefinition } from "../../../lib/agents";
import { compareEvaluationRuns, createEvaluationCase, createEvaluationRun, fetchEvaluationCases, fetchEvaluationDataset, fetchEvaluationResults, fetchEvaluationRuns, type EvaluationCase, type EvaluationDataset, type EvaluationResult, type EvaluationRun, type EvaluatorType } from "../../../lib/evaluations";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };
type ComparisonMetricKey = "pass_rate" | "run_success_rate" | "quality_score" | "average_latency_ms" | "total_tokens" | "estimated_cost" | "tool_correctness";
type ComparisonMetric = { key: ComparisonMetricKey; label: string; unit: "percent" | "milliseconds" | "tokens" | "currency"; direction: "higher" | "lower"; guidance: string };
const comparisonMetrics: ComparisonMetric[] = [
  { key: "pass_rate", label: "Pass rate", unit: "percent", direction: "higher", guidance: "Higher means more cases passed." },
  { key: "run_success_rate", label: "Run success", unit: "percent", direction: "higher", guidance: "Higher means more cases completed successfully." },
  { key: "quality_score", label: "Quality", unit: "percent", direction: "higher", guidance: "Higher means stronger evaluator scores." },
  { key: "average_latency_ms", label: "Average latency", unit: "milliseconds", direction: "lower", guidance: "Lower means faster responses." },
  { key: "total_tokens", label: "Tokens used", unit: "tokens", direction: "lower", guidance: "Lower usually means less model usage." },
  { key: "estimated_cost", label: "Estimated cost", unit: "currency", direction: "lower", guidance: "Lower means less estimated spend." },
  { key: "tool_correctness", label: "Tool correctness", unit: "percent", direction: "higher", guidance: "Higher means more expected tool calls were correct." },
];
const evaluatorOptions: Array<{ type: EvaluatorType; label: string; description: string }> = [
  { type: "EXACT_MATCH", label: "Exact match", description: "Output equals the expected text." },
  { type: "CONTAINS", label: "Contains", description: "Output contains the expected phrase." },
  { type: "JSON_SCHEMA", label: "JSON schema", description: "Output matches the case schema." },
  { type: "TOOL_CALL", label: "Tool call", description: "Agent called the expected tool." },
  { type: "LATENCY", label: "Latency", description: "Run completed within a time limit." },
  { type: "LLM_JUDGE", label: "LLM judge", description: "A separate model grades a rubric." },
  { type: "GROUNDEDNESS", label: "Groundedness", description: "A judge checks answer claims against citations." },
];

export default function EvaluationDatasetPage() {
  const params = useParams<{ datasetId: string }>();
  const datasetId = params.datasetId;
  const router = useRouter();
  const addCaseTriggerRef = useRef<HTMLButtonElement>(null);
  const closeCaseModalRef = useRef<HTMLButtonElement>(null);
  const caseModalRef = useRef<HTMLElement>(null);
  const comparisonTriggerRef = useRef<HTMLButtonElement>(null);
  const closeComparisonModalRef = useRef<HTMLButtonElement>(null);
  const comparisonModalRef = useRef<HTMLElement>(null);
  const savingCaseRef = useRef(false);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [dataset, setDataset] = useState<EvaluationDataset | null>(null);
  const [cases, setCases] = useState<EvaluationCase[]>([]);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [results, setResults] = useState<EvaluationResult[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [versions, setVersions] = useState<AgentVersionSummary[]>([]);
  const [models, setModels] = useState<ModelDefinition[]>([]);
  const [selectedAgent, setSelectedAgent] = useState("");
  const [selectedVersion, setSelectedVersion] = useState("");
  const [selectedEvaluators, setSelectedEvaluators] = useState<EvaluatorType[]>([]);
  const [judgeModel, setJudgeModel] = useState("");
  const [latencyLimit, setLatencyLimit] = useState("10000");
  const [input, setInput] = useState("");
  const [expected, setExpected] = useState("");
  const [expectedTool, setExpectedTool] = useState("");
  const [expectedSchema, setExpectedSchema] = useState("");
  const [rubric, setRubric] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingCase, setSavingCase] = useState(false);
  const [addCaseOpen, setAddCaseOpen] = useState(false);
  const [caseError, setCaseError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [comparison, setComparison] = useState<Awaited<ReturnType<typeof compareEvaluationRuns>> | null>(null);
  const [comparing, setComparing] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [comparisonModalOpen, setComparisonModalOpen] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  const loadDataset = useCallback(async () => {
    const [nextDataset, nextCases, nextRuns] = await Promise.all([
      fetchEvaluationDataset(datasetId), fetchEvaluationCases(datasetId), fetchEvaluationRuns(datasetId),
    ]);
    setDataset(nextDataset); setCases(nextCases); setRuns(nextRuns);
    const active = nextRuns.find((run) => run.status === "QUEUED" || run.status === "RUNNING");
    const target = active?.id ?? nextRuns[0]?.id ?? "";
    setSelectedRunId((current) => current || target);
    const completedRuns = nextRuns.filter((run) => run.status === "COMPLETED");
    setBaselineId((current) => current || completedRuns[1]?.id || completedRuns[0]?.id || "");
    setCandidateId((current) => current || completedRuns[0]?.id || "");
  }, [datasetId]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await apiFetch("/v1/workspaces");
        if (!response.ok) throw new Error(await readApiError(response));
        const body = await response.json() as { data: Workspace[] };
        const saved = window.localStorage.getItem("vf-workspace-id");
        const selected = body.data.find((item) => item.id === saved) ?? body.data[0] ?? null;
        if (!selected) throw new Error("No workspace is available for this account.");
        const [agentList, modelList] = await Promise.all([fetchAgents(selected.id), fetchModels()]);
        await loadDataset();
        if (cancelled) return;
        setWorkspace(selected); setAgents(agentList); setModels(modelList);
        setSelectedAgent("");
        setJudgeModel(modelList[0] ? `${modelList[0].provider}:${modelList[0].name}` : "");
      } catch (reason: unknown) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load this evaluation dataset.");
      } finally { if (!cancelled) setLoading(false); }
    }
    void load();
    return () => { cancelled = true; };
  }, [loadDataset]);

  useEffect(() => {
    if (!selectedAgent) { setVersions([]); setSelectedVersion(""); return; }
    let cancelled = false;
    void fetchVersions(selectedAgent).then((items) => {
      if (!cancelled) { setVersions(items); setSelectedVersion(items[0]?.id ?? ""); }
    }).catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load agent versions."); });
    return () => { cancelled = true; };
  }, [selectedAgent]);

  useEffect(() => {
    const activeRun = runs.find((run) => run.status === "QUEUED" || run.status === "RUNNING");
    if (!activeRun) return;
    const timer = window.setInterval(() => { void loadDataset().catch(() => undefined); }, 2500);
    return () => window.clearInterval(timer);
  }, [runs, loadDataset]);

  useEffect(() => {
    if (!selectedRunId) { setResults([]); return; }
    let cancelled = false;
    void fetchEvaluationResults(selectedRunId).then((items) => { if (!cancelled) setResults(items); }).catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load results."); });
    return () => { cancelled = true; };
  }, [selectedRunId, runs]);

  useEffect(() => {
    if (!addCaseOpen) return;

    const previousOverflow = document.body.style.overflow;
    const trigger = addCaseTriggerRef.current;
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(() => closeCaseModalRef.current?.focus());

    function focusableElements() {
      return Array.from(
        caseModalRef.current?.querySelectorAll<HTMLElement>(
          "button:not([disabled]), input:not([disabled]), textarea:not([disabled])",
        ) ?? [],
      );
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !savingCaseRef.current) {
        event.preventDefault();
        setAddCaseOpen(false);
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
  }, [addCaseOpen]);

  useEffect(() => {
    if (!comparisonModalOpen || !comparison) return;

    const previousOverflow = document.body.style.overflow;
    const trigger = comparisonTriggerRef.current;
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(() => closeComparisonModalRef.current?.focus());

    function focusableElements() {
      return Array.from(
        comparisonModalRef.current?.querySelectorAll<HTMLElement>(
          "button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex='-1'])",
        ) ?? [],
      );
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setComparisonModalOpen(false);
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
  }, [comparisonModalOpen, comparison]);

  const judgeOptions = useMemo(() => models.map((model) => ({ value: `${model.provider}:${model.name}`, label: model.display_name, secondary: model.provider })), [models]);
  const versionsOptions = versions.map((version) => ({ value: version.id, label: `v${version.version_number}`, secondary: version.change_note ?? "Published version" }));
  const agentOptions = agents.map((agent) => ({ value: agent.id, label: agent.name, secondary: agent.slug }));
  const completedRuns = runs.filter((run) => run.status === "COMPLETED");
  const runOptions = runs.map((run) => {
    const evaluators = run.evaluators.map((evaluator) => {
      if (evaluator.type === "LATENCY") {
        const limit = evaluator.config.max_ms;
        return `Latency${typeof limit === "number" ? ` ≤ ${integer(limit)} ms` : ""}`;
      }
      return evaluatorOptions.find((option) => option.type === evaluator.type)?.label ?? evaluator.type;
    });
    const caseCount = run.aggregate_metrics.case_count;
    const agentName = agents.find((agent) => agent.id === run.agent_id)?.name;
    const summary = [agentName, typeof caseCount === "number" ? `${caseCount} cases` : null, evaluators.join(" + ")].filter(Boolean).join(" · ");
    return { value: run.id, label: `${run.status} · ${new Date(run.created_at).toLocaleString()}`, secondary: summary };
  });
  const selectedBaselineRun = runs.find((run) => run.id === baselineId);
  const selectedCandidateRun = runs.find((run) => run.id === candidateId);
  const comparisonEligibilityMessages: string[] = [];
  if (selectedBaselineRun && selectedCandidateRun) {
    if (selectedBaselineRun.id === selectedCandidateRun.id) {
      comparisonEligibilityMessages.push("Choose two different runs to compare.");
    }
    if (selectedBaselineRun.agent_id !== selectedCandidateRun.agent_id) {
      comparisonEligibilityMessages.push("Both runs must use the same agent.");
    }
    if (selectedBaselineRun.evaluation_dataset_id !== selectedCandidateRun.evaluation_dataset_id) {
      comparisonEligibilityMessages.push("Both runs must belong to the same dataset.");
    }
    const baselineCaseCount = selectedBaselineRun.aggregate_metrics.case_count;
    const candidateCaseCount = selectedCandidateRun.aggregate_metrics.case_count;
    if (typeof baselineCaseCount === "number" && typeof candidateCaseCount === "number" && baselineCaseCount !== candidateCaseCount) {
      comparisonEligibilityMessages.push(`These runs used different case snapshots (${baselineCaseCount} vs ${candidateCaseCount} cases).`);
    }
    if (JSON.stringify(selectedBaselineRun.evaluators) !== JSON.stringify(selectedCandidateRun.evaluators)) {
      comparisonEligibilityMessages.push("The evaluator selections or settings differ.");
    }
  }
  const comparisonEligibilityMessage = comparisonEligibilityMessages.join(" ");
  const pickedJudge = judgeModel.split(":");
  const pickedJudgeConfig = { provider: pickedJudge[0] ?? "", model: pickedJudge[1] ?? "", criteria: ["correctness", "groundedness"], pass_threshold: 0.7 };
  const selectedRun = runs.find((run) => run.id === selectedRunId);
  const judgeUsage = selectedRun?.aggregate_metrics.judge_usage as { input_tokens?: number; output_tokens?: number } | undefined;

  async function handleAddCase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingCase || !input.trim()) return;
    setSavingCase(true); savingCaseRef.current = true; setCaseError(null); setError(null); setMessage(null);
    try {
      let parsedSchema: Record<string, unknown> | null = null;
      if (expectedSchema.trim()) {
        const parsed: unknown = JSON.parse(expectedSchema);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Expected schema must be a JSON object.");
        parsedSchema = parsed as Record<string, unknown>;
      }
      const createdCase = await createEvaluationCase(datasetId, { input: { type: "text", text: input.trim() }, expected_output: expected.trim() ? { text: expected.trim() } : null, expected_tool: expectedTool.trim() || null, expected_schema: parsedSchema, rubric: rubric.trim() || null });
      setCases((current) => [...current, createdCase].sort((first, second) => first.position - second.position));
      setDataset((current) => current ? { ...current, case_count: current.case_count + 1, updated_at: new Date().toISOString() } : current);
      setInput(""); setExpected(""); setExpectedTool(""); setExpectedSchema(""); setRubric("");
      setAddCaseOpen(false); setMessage("Case added to the dataset.");
    } catch (reason: unknown) { setCaseError(reason instanceof Error ? reason.message : "Unable to add case."); }
    finally { setSavingCase(false); savingCaseRef.current = false; }
  }

  function openAddCase() {
    setCaseError(null);
    setInput(""); setExpected(""); setExpectedTool(""); setExpectedSchema(""); setRubric("");
    setAddCaseOpen(true);
  }

  async function handleRun() {
    if (!selectedVersion || !selectedEvaluators.length || running) return;
    setRunning(true); setError(null); setMessage(null);
    try {
      const evaluators = selectedEvaluators.map((type) => ({
        type,
        config: type === "LATENCY" ? { max_ms: Number(latencyLimit) } : type === "LLM_JUDGE" || type === "GROUNDEDNESS" ? pickedJudgeConfig : {},
      }));
      const run = await createEvaluationRun(datasetId, { agent_version_id: selectedVersion, evaluators });
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setSelectedRunId(run.id); setMessage("Evaluation queued. Progress will update automatically.");
    } catch (reason: unknown) { setError(reason instanceof Error ? reason.message : "Unable to start evaluation."); }
    finally { setRunning(false); }
  }

  async function handleCompare() {
    if (!baselineId || !candidateId || baselineId === candidateId) return;
    setComparing(true); setCompareError(null); setComparison(null);
    try { setComparison(await compareEvaluationRuns(baselineId, candidateId)); }
    catch (reason: unknown) {
      const message = reason instanceof Error ? reason.message : "Unable to compare evaluation runs.";
      setCompareError(message.includes("same agent and dataset snapshot")
        ? "These runs use different comparison settings. Choose runs for the same agent and the exact same saved case snapshot, with identical evaluators and limits."
        : message);
    }
    finally { setComparing(false); }
  }

  function toggleCompare() {
    setCompareOpen((current) => !current);
    setCompareError(null);
    setComparison(null);
    setComparisonModalOpen(false);
  }

  function toggleEvaluator(type: EvaluatorType) {
    setSelectedEvaluators((current) => current.includes(type) ? current.filter((item) => item !== type) : [...current, type]);
  }

  return <AppShell><div className="page-content evaluation-page evaluation-detail-page">
    <div className="page-header"><div><button type="button" className="text-button evaluation-back" onClick={() => router.push("/evaluations")}><ArrowLeft size={14} aria-hidden="true" />All evaluations</button><p className="eyebrow">VibesFactory / Evaluate</p><h1>{dataset?.name ?? "Evaluation dataset"}</h1><p className="page-description">{dataset?.description || "Build a repeatable quality suite and compare published agent versions."}</p></div><span className="status-badge info"><span aria-hidden="true" />{cases.length} {cases.length === 1 ? "case" : "cases"}</span></div>
    {error ? <div className="form-error agent-alert" role="alert" aria-live="polite"><CircleAlert size={16} aria-hidden="true" />{error}<button type="button" className="icon-button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={15} aria-hidden="true" /></button></div> : null}
    {message ? <div className="evaluation-message" role="status" aria-live="polite"><Check size={15} aria-hidden="true" />{message}</div> : null}
    {loading ? <section className="panel agent-state"><LoaderCircle className="spin" size={18} aria-hidden="true" />Loading evaluation dataset…</section> : <>
      <div className="evaluation-workbench">
        <section className="panel evaluation-cases-panel"><div className="panel-heading"><div><span className="panel-kicker">{cases.length} test cases</span><h2>Cases</h2></div><div className="evaluation-cases-actions"><button ref={addCaseTriggerRef} type="button" className="button secondary-button evaluation-add-case-button" onClick={openAddCase}><Plus size={15} aria-hidden="true" />Add test case</button><button type="button" className="icon-button" aria-label="Refresh cases" onClick={() => void loadDataset()}><RefreshCw size={15} aria-hidden="true" /></button></div></div>
          {cases.length === 0 ? <div className="evaluation-empty compact evaluation-cases-empty"><FlaskConical size={22} aria-hidden="true" /><strong>No test cases yet</strong><span>Add a representative question to start checking your agent.</span></div> : <div className="evaluation-table-scroll evaluation-cases-scroll"><table className="evaluation-table"><thead><tr><th>Case</th><th>Input</th><th>Expected behavior</th></tr></thead><tbody>{cases.map((item) => <tr key={item.id}><td className="evaluation-case-position">{String(item.position).padStart(2, "0")}</td><td>{item.input.text}</td><td>{[item.expected_output?.text, item.expected_tool ? `tool: ${item.expected_tool}` : null, item.rubric ? "rubric" : null].filter(Boolean).join(" · ") || <span className="text-muted">No expected value</span>}</td></tr>)}</tbody></table></div>}
        </section>
        <section className="panel evaluation-launch-panel"><div className="panel-heading"><div><span className="panel-kicker">Run against a snapshot</span><h2>Evaluate a version</h2></div><FlaskConical size={19} aria-hidden="true" /></div>
          <div className="evaluation-form evaluation-run-form">
            <label className="evaluation-field">Agent<PrimarySelect value={selectedAgent} options={agentOptions} placeholder="Select an agent" ariaLabel="Agent" onChange={setSelectedAgent} searchable searchPlaceholder="Search agents…" emptyMessage="No matching agents in this workspace." /></label>
            <label className="evaluation-field">Published version<PrimarySelect value={selectedVersion} options={versionsOptions} placeholder="Select a version" ariaLabel="Published agent version" onChange={setSelectedVersion} emptyMessage="Publish an agent version first." /></label>
            <fieldset className="evaluation-selector"><legend>Evaluators</legend><div className="evaluation-evaluator-grid">{evaluatorOptions.map((item) => <button className={`evaluation-evaluator-option ${selectedEvaluators.includes(item.type) ? "selected" : ""}`} type="button" key={item.type} aria-pressed={selectedEvaluators.includes(item.type)} onClick={() => toggleEvaluator(item.type)}><span className="evaluation-check">{selectedEvaluators.includes(item.type) ? <Check size={12} aria-hidden="true" /> : null}</span><span><strong>{item.label}</strong><small>{item.description}</small></span></button>)}</div>{selectedEvaluators.length === 0 ? <small className="evaluation-evaluator-hint">Choose at least one check to enable the evaluation.</small> : null}</fieldset>
            {selectedEvaluators.includes("LATENCY") ? <label className="evaluation-field">Latency limit <span>(milliseconds)</span><PrimaryTextInput type="number" min={1} max={3600000} value={latencyLimit} onChange={(event) => setLatencyLimit(event.target.value)} /></label> : null}
            {selectedEvaluators.some((type) => type === "LLM_JUDGE" || type === "GROUNDEDNESS") ? <label className="evaluation-field">Judge model<PrimarySelect value={judgeModel} options={judgeOptions} placeholder="Choose a configured model" ariaLabel="LLM judge model" onChange={setJudgeModel} emptyMessage="No judge model is available." /><small>The judge receives the case, agent answer, rubric, and citations when available. Its usage is recorded separately.</small></label> : null}
            <div className="evaluation-safety-note"><CircleAlert size={15} aria-hidden="true" /><span>Runs use the shared agent runtime, keep each case in a fresh session, and do not read or write long-term memory. Versions with side-effecting tools are blocked.</span></div>
            <button className="button primary-button" type="button" onClick={() => void handleRun()} disabled={running || !cases.length || !selectedVersion || !selectedEvaluators.length || (selectedEvaluators.some((type) => type === "LLM_JUDGE" || type === "GROUNDEDNESS") && !judgeModel)}>{running ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <FlaskConical size={15} aria-hidden="true" />}{running ? "Queueing…" : "Start evaluation"}</button>
          </div>
        </section>
      </div>

      <section className="panel evaluation-results-panel">
        <div className="panel-heading">
          <div><span className="panel-kicker">Batch history</span><h2>Results</h2><p className="panel-copy">Every case links to its normal runtime run and trace.</p></div>
          <div className="evaluation-results-actions">
            {runs.length ? <label className="evaluation-field evaluation-run-picker">Selected run<PrimarySelect value={selectedRunId} options={runOptions} placeholder="Choose a run" ariaLabel="Selected evaluation run" onChange={setSelectedRunId} /></label> : null}
            {completedRuns.length > 1 ? <button className="button secondary-button evaluation-compare-trigger" type="button" aria-expanded={compareOpen} aria-controls={compareOpen ? "evaluation-compare-inline" : undefined} onClick={toggleCompare}><Scale size={15} aria-hidden="true" />{compareOpen ? "Hide comparison" : "Compare runs"}</button> : null}
          </div>
        </div>
        {compareOpen && completedRuns.length > 1 ? <section id="evaluation-compare-inline" className="evaluation-compare-inline" aria-labelledby="evaluation-compare-title">
          <div className="evaluation-compare-inline-heading"><div><span className="panel-kicker">Regression check</span><h3 id="evaluation-compare-title">Compare completed runs</h3><p className="panel-copy">Choose two runs made with the same agent, saved cases, and evaluator settings.</p></div><Scale size={18} aria-hidden="true" /></div>
          <div className="evaluation-compare-controls">
            <label className="evaluation-field">Baseline run<PrimarySelect value={baselineId} options={runOptions.filter((item) => completedRuns.some((run) => run.id === item.value))} placeholder="Select baseline" ariaLabel="Baseline evaluation run" onChange={(value) => { setBaselineId(value); setCompareError(null); setComparison(null); }} /></label>
            <label className="evaluation-field">Candidate run<PrimarySelect value={candidateId} options={runOptions.filter((item) => completedRuns.some((run) => run.id === item.value))} placeholder="Select candidate" ariaLabel="Candidate evaluation run" onChange={(value) => { setCandidateId(value); setCompareError(null); setComparison(null); }} /></label>
            <button className="button primary-button" type="button" onClick={() => void handleCompare()} disabled={comparing || !baselineId || !candidateId || Boolean(comparisonEligibilityMessage)}>{comparing ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Scale size={15} aria-hidden="true" />}{comparing ? "Comparing…" : "Compare runs"}</button>
          </div>
          {compareError || comparisonEligibilityMessage ? <div className="evaluation-compare-error" role={compareError ? "alert" : "status"} aria-live="polite"><CircleAlert size={16} aria-hidden="true" /><div><strong>{compareError ? "Comparison failed" : "These runs can’t be compared yet"}</strong><span>{compareError ?? comparisonEligibilityMessage} {compareError ? "Choose another run pair or rerun both with matching settings." : "Use two runs with the same agent, exact saved case snapshot, and evaluator configuration. Rerun one if needed."}</span></div></div> : null}
          {comparison ? <div className="evaluation-comparison-ready" role="status" aria-live="polite"><span className="evaluation-comparison-ready-copy"><CheckCircle2 size={18} aria-hidden="true" /><span><strong>Comparison ready</strong><small>Review both runs side by side, with clear values and whether each change improved or regressed.</small></span></span><button ref={comparisonTriggerRef} className="button secondary-button" type="button" aria-haspopup="dialog" onClick={() => setComparisonModalOpen(true)}><Scale size={15} aria-hidden="true" />Open detailed comparison</button></div> : null}
        </section> : null}
        {!runs.length ? <div className="evaluation-empty compact"><Clock3 size={21} aria-hidden="true" /><strong>No runs yet</strong><span>Start an evaluation to see its scorecard here.</span></div> : <>
          {selectedRun ? <div className="evaluation-run-summary"><span className={`status-badge ${selectedRun.status === "COMPLETED" ? "success" : selectedRun.status === "FAILED" ? "error" : "info"}`}><span aria-hidden="true" />{selectedRun.status}</span><Metric label="Pass rate" value={percent(selectedRun.aggregate_metrics.pass_rate)} /><Metric label="Run success" value={percent(selectedRun.aggregate_metrics.run_success_rate)} /><Metric label="Quality" value={percent(selectedRun.aggregate_metrics.quality_score)} /><Metric label="Average latency" value={duration(selectedRun.aggregate_metrics.average_latency_ms)} /><Metric label="Tokens" value={integer(selectedRun.aggregate_metrics.total_tokens)} /><Metric label="Estimated cost" value={money(selectedRun.aggregate_metrics.estimated_cost)} /><Metric label="Judge tokens" value={integer((judgeUsage?.input_tokens ?? 0) + (judgeUsage?.output_tokens ?? 0))} /><Metric label="Unscored cases" value={integer(selectedRun.aggregate_metrics.unscored_case_count)} />{selectedRun.error ? <span className="evaluation-run-error">{selectedRun.error.message}</span> : null}</div> : null}
          {results.length ? <div className="evaluation-table-scroll"><table className="evaluation-table"><thead><tr><th>Case</th><th>Evaluator</th><th>Score</th><th>Result</th><th>Details</th><th>Runtime run</th></tr></thead><tbody>{results.map((result) => <tr key={result.id}><td>{result.case.position}. {result.case.input.text}</td><td><span className="evaluation-code">{result.evaluator}</span></td><td>{result.score === null ? "—" : `${Math.round(result.score * 100)}%`}</td><td>{result.passed === null ? <span className="status-badge muted"><span aria-hidden="true" />Unscored</span> : <span className={`status-badge ${result.passed ? "success" : "error"}`}><span aria-hidden="true" />{result.passed ? "Pass" : "Fail"}</span>}</td><td>{String(result.details.reason ?? result.details.errors?.toString() ?? result.details.latency_ms ?? "—")}</td><td>{result.trace_id ? <a className="text-button" href={`/traces/${result.trace_id}`}>{result.run_id?.slice(0, 8) ?? "Trace"} ↗</a> : "—"}</td></tr>)}</tbody></table></div> : selectedRun?.status === "RUNNING" || selectedRun?.status === "QUEUED" ? <div className="agent-state"><LoaderCircle className="spin" size={17} aria-hidden="true" />Cases are running. Results update as they finish.</div> : null}
        </>}
      </section>

      {addCaseOpen ? <div className="modal-backdrop evaluation-modal-backdrop evaluation-case-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !savingCase) setAddCaseOpen(false); }}>
        <section ref={caseModalRef} className="modal-dialog evaluation-create-modal evaluation-case-modal" role="dialog" aria-modal="true" aria-labelledby="evaluation-case-title" aria-describedby="evaluation-case-description" aria-busy={savingCase}>
          <header className="modal-heading"><div><p className="panel-kicker">Dataset design</p><h2 id="evaluation-case-title">Add a test case</h2><p id="evaluation-case-description" className="panel-copy">Write a realistic question, then add any checks that should stay consistent across agent versions.</p></div><button ref={closeCaseModalRef} className="icon-button modal-close" type="button" aria-label="Close add test case dialog" disabled={savingCase} onClick={() => setAddCaseOpen(false)}><X size={16} aria-hidden="true" /></button></header>
          {caseError ? <div className="form-error evaluation-modal-error" role="alert" aria-live="polite">{caseError}</div> : null}
          <form className="modal-form evaluation-modal-form evaluation-case-modal-form" onSubmit={(event) => void handleAddCase(event)}>
            <label className="evaluation-modal-field evaluation-modal-field-wide" htmlFor="evaluation-case-input"><span>Input <em>required</em></span><PrimaryTextArea id="evaluation-case-input" value={input} onChange={(event) => { setInput(event.target.value); if (caseError) setCaseError(null); }} rows={3} maxLength={100000} required placeholder="What is the refund window?" disabled={savingCase} /></label>
            <label className="evaluation-modal-field" htmlFor="evaluation-case-expected"><span>Expected output <em>optional</em></span><PrimaryTextArea id="evaluation-case-expected" value={expected} onChange={(event) => setExpected(event.target.value)} rows={3} placeholder="30 days" disabled={savingCase} /></label>
            <label className="evaluation-modal-field" htmlFor="evaluation-case-tool"><span>Expected tool <em>optional</em></span><PrimaryTextInput id="evaluation-case-tool" value={expectedTool} onChange={(event) => setExpectedTool(event.target.value)} maxLength={255} placeholder="search_knowledge" disabled={savingCase} /></label>
            <label className="evaluation-modal-field" htmlFor="evaluation-case-schema"><span>Expected JSON schema <em>optional</em></span><PrimaryTextArea id="evaluation-case-schema" value={expectedSchema} onChange={(event) => setExpectedSchema(event.target.value)} rows={3} placeholder={'{"type":"object","required":["answer"]}'} disabled={savingCase} /></label>
            <label className="evaluation-modal-field evaluation-modal-field-wide" htmlFor="evaluation-case-rubric"><span>Judge rubric <em>optional</em></span><PrimaryTextArea id="evaluation-case-rubric" value={rubric} onChange={(event) => setRubric(event.target.value)} rows={3} maxLength={10000} placeholder="Answer must be accurate and grounded in the policy." disabled={savingCase} /></label>
            <p className="field-helper">Expected values are optional. Add only the checks that make sense for this question.</p>
            <div className="modal-actions"><button className="button secondary-button" type="button" disabled={savingCase} onClick={() => setAddCaseOpen(false)}>Cancel</button><button className="button primary-button" type="submit" disabled={savingCase || !input.trim()}>{savingCase ? <LoaderCircle size={15} className="spin" aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}{savingCase ? "Adding…" : "Add test case"}</button></div>
          </form>
        </section>
      </div> : null}
      {comparisonModalOpen && comparison ? <div className="modal-backdrop evaluation-modal-backdrop evaluation-compare-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setComparisonModalOpen(false); }}>
        <section ref={comparisonModalRef} className="modal-dialog evaluation-compare-modal" role="dialog" aria-modal="true" aria-labelledby="evaluation-comparison-modal-title" aria-describedby="evaluation-comparison-modal-description">
          <header className="modal-heading evaluation-comparison-modal-heading"><div><p className="panel-kicker">Run comparison</p><h2 id="evaluation-comparison-modal-title">Detailed comparison</h2><p id="evaluation-comparison-modal-description" className="panel-copy">Compare the actual results for each quality criterion. A change is measured from the baseline run to the candidate run.</p></div><button ref={closeComparisonModalRef} className="icon-button modal-close" type="button" aria-label="Close detailed comparison" onClick={() => setComparisonModalOpen(false)}><X size={16} aria-hidden="true" /></button></header>
          <div className="evaluation-comparison-run-legend" aria-label="Runs being compared">
            <span className="evaluation-comparison-run-chip baseline"><i aria-hidden="true" /><span><strong>Baseline</strong><small>{selectedBaselineRun ? new Date(selectedBaselineRun.created_at).toLocaleString() : "Earlier run"}</small></span></span>
            <span className="evaluation-comparison-run-chip candidate"><i aria-hidden="true" /><span><strong>Candidate</strong><small>{selectedCandidateRun ? new Date(selectedCandidateRun.created_at).toLocaleString() : "Compared run"}</small></span></span>
          </div>
          <p className="evaluation-comparison-explainer"><strong>How to read this:</strong> Each row shows a run’s value. The change below compares candidate with baseline. Higher pass, success, quality, and tool correctness scores are better; lower latency, token use, and cost are usually better.</p>
          <div className="evaluation-comparison-chart-grid">
            {comparisonMetrics.map((metric) => <ComparisonChart key={metric.key} metric={metric} baseline={comparison.baseline.metrics[metric.key]} candidate={comparison.candidate.metrics[metric.key]} />)}
          </div>
          <footer className="evaluation-comparison-modal-footer"><span>“No data” means that metric was not recorded for one or both runs.</span><button className="button secondary-button" type="button" onClick={() => setComparisonModalOpen(false)}>Close</button></footer>
        </section>
      </div> : null}
    </>}</div></AppShell>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="evaluation-metric"><small>{label}</small><strong>{value}</strong></div>; }
function percent(value: unknown) { return typeof value === "number" ? `${Math.round(value * 100)}%` : "—"; }
function integer(value: unknown) { return typeof value === "number" ? new Intl.NumberFormat().format(value) : "—"; }
function duration(value: unknown) { return typeof value === "number" ? `${Math.round(value)} ms` : "—"; }
function money(value: unknown) { return typeof value === "number" ? `$${value.toFixed(5)}` : "—"; }
function ComparisonChart({ metric, baseline, candidate }: { metric: ComparisonMetric; baseline: number | null | undefined; candidate: number | null | undefined }) {
  const baselineValue = typeof baseline === "number" ? baseline : null;
  const candidateValue = typeof candidate === "number" ? candidate : null;
  const maximum = metric.unit === "percent" ? 1 : Math.max(baselineValue ?? 0, candidateValue ?? 0);
  const barWidth = (value: number | null) => value === null || maximum <= 0 ? 0 : Math.max(0, Math.min(100, (value / maximum) * 100));
  const change = baselineValue !== null && candidateValue !== null ? candidateValue - baselineValue : null;
  const changeStatus = change === null ? "No data" : change === 0 ? "No change" : (metric.direction === "higher" ? change > 0 : change < 0) ? "Improved" : "Regressed";
  const statusClass = changeStatus.toLowerCase().replace(" ", "-");

  return <article className="evaluation-comparison-chart-card" aria-labelledby={`comparison-${metric.key}-title`}>
    <header className="evaluation-comparison-chart-heading"><div><h3 id={`comparison-${metric.key}-title`}>{metric.label}</h3><p>{metric.guidance}</p></div><span className={`evaluation-comparison-status ${statusClass}`}>{changeStatus}</span></header>
    <div className="evaluation-comparison-bars" role="group" aria-label={`${metric.label}: baseline ${formatComparisonValue(metric, baselineValue)}, candidate ${formatComparisonValue(metric, candidateValue)}`}>
      <ComparisonBar label="Baseline" value={baselineValue} width={barWidth(baselineValue)} metric={metric} variant="baseline" />
      <ComparisonBar label="Candidate" value={candidateValue} width={barWidth(candidateValue)} metric={metric} variant="candidate" />
    </div>
    <div className={`evaluation-comparison-change ${statusClass}`}><span>Change from baseline</span><strong>{formatComparisonChange(metric, change)}</strong></div>
  </article>;
}

function ComparisonBar({ label, value, width, metric, variant }: { label: string; value: number | null; width: number; metric: ComparisonMetric; variant: "baseline" | "candidate" }) {
  return <div className={`evaluation-comparison-bar-row ${variant}`}><span className="evaluation-comparison-bar-label">{label}</span><span className="evaluation-comparison-track" aria-hidden="true"><i style={{ width: `${width}%` }} /></span><strong>{formatComparisonValue(metric, value)}</strong></div>;
}

function formatComparisonValue(metric: ComparisonMetric, value: number | null) {
  if (value === null) return "No data";
  if (metric.unit === "percent") return `${Math.round(value * 100)}%`;
  if (metric.unit === "milliseconds") return `${integer(value)} ms`;
  if (metric.unit === "tokens") return integer(value);
  return money(value);
}

function formatComparisonChange(metric: ComparisonMetric, value: number | null) {
  if (value === null) return "Not available";
  if (value === 0) return "No change";
  const sign = value > 0 ? "+" : "−";
  const absolute = Math.abs(value);
  if (metric.unit === "percent") return `${sign}${Math.round(absolute * 100)} percentage points`;
  if (metric.unit === "milliseconds") return `${sign}${integer(absolute)} ms`;
  if (metric.unit === "tokens") return `${sign}${integer(absolute)} tokens`;
  return `${sign}$${absolute.toFixed(5)}`;
}
