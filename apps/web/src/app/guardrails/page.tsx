"use client";

import {
    AlertCircle,
    Check,
    FileCode2,
    LoaderCircle,
    Plus,
    ShieldCheck,
    SlidersHorizontal,
    X,
} from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { AppShell } from "../../components/app-shell";
import { apiFetch, readApiError } from "../../lib/api";
import {
    createGuardrailPolicy,
    createGuardrailVersion,
    fetchGuardrails,
    type GuardrailHook,
    type GuardrailPolicy,
    type GuardrailRule,
} from "../../lib/guardrails";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };

const hooks: GuardrailHook[] = [
    "INPUT",
    "MODEL_OUTPUT",
    "TOOL_INPUT",
    "TOOL_OUTPUT",
];

const baselineRules = [
    ["Secret detection", "Redacts recognizable credentials and token-shaped values."],
    ["PII redaction", "Redacts email, phone, and Luhn-valid payment-card candidates."],
    ["Payload limits", "Blocks input/tool input over 100 KB and output over 256 KB."],
    ["Tool risk", "Blocks HIGH-risk side-effect tools until approval support ships."],
] as const;

function newRule(): GuardrailRule {
    return {
        id: "custom-rule",
        type: "REGEX",
        action: "BLOCK",
        hooks: ["INPUT"],
        pattern: "",
        replacement: "[REDACTED]",
    };
}

function hookLabel(hook: GuardrailHook) {
    return hook.replace("_", " ");
}

function PolicyCard({ policy }: { policy: GuardrailPolicy }) {
    return (
        <article className="guardrail-policy-card">
            <div className="guardrail-policy-card-topline">
                <span className="guardrail-policy-icon" aria-hidden="true">
                    <FileCode2 size={17} />
                </span>
                <span className="status-badge info"><span />Workspace policy</span>
            </div>
            <div className="guardrail-policy-card-heading">
                <div>
                    <h3>{policy.name}</h3>
                    <p>{policy.description || "No description yet."}</p>
                </div>
                <span className="guardrail-version-badge">v{policy.latest_version_number || "—"}</span>
            </div>
            <div className="guardrail-policy-tags">
                <span>Immutable versions</span>
                <span>{policy.usage_count} active binding{policy.usage_count === 1 ? "" : "s"}</span>
            </div>
            <footer className="guardrail-policy-card-footer">
                <span>Latest version</span>
                <code>{policy.latest_version_number ? `v${policy.latest_version_number}` : "Not published"}</code>
            </footer>
        </article>
    );
}

function BaselineCard() {
    return (
        <article className="guardrail-policy-card guardrail-baseline-policy-card">
            <div className="guardrail-policy-card-topline">
                <span className="guardrail-policy-icon baseline" aria-hidden="true"><ShieldCheck size={17} /></span>
                <span className="status-badge success"><span />Enabled by default</span>
            </div>
            <div className="guardrail-policy-card-heading">
                <div><h3>Platform default</h3><p>Balanced protection, managed by VibesFactory.</p></div>
                <span className="guardrail-version-badge">v1</span>
            </div>
            <div className="guardrail-baseline-rules">
                {baselineRules.map(([title, description]) => (
                    <div className="guardrail-baseline-rule" key={title}>
                        <Check size={14} aria-hidden="true" /><span><strong>{title}</strong><small>{description}</small></span>
                    </div>
                ))}
            </div>
            <footer className="guardrail-policy-card-footer"><span>Source</span><code>PLATFORM_DEFAULT</code></footer>
        </article>
    );
}

function GuardrailPolicyDialog({
    open,
    workspace,
    onClose,
    onCreated,
}: {
    open: boolean;
    workspace: Workspace | null;
    onClose: () => void;
    onCreated: (policy: GuardrailPolicy) => void;
}) {
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [rule, setRule] = useState<GuardrailRule>(newRule);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const dialogRef = useRef<HTMLElement>(null);
    const errorRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        window.requestAnimationFrame(() => dialogRef.current?.querySelector<HTMLElement>("input")?.focus());
        function focusableElements() {
            return Array.from(dialogRef.current?.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled])") ?? []);
        }
        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape" && !busy) { event.preventDefault(); onClose(); return; }
            if (event.key !== "Tab") return;
            const elements = focusableElements();
            if (!elements.length) return;
            const first = elements[0];
            const last = elements[elements.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
        window.addEventListener("keydown", handleKeyDown);
        return () => { document.body.style.overflow = previousOverflow; window.removeEventListener("keydown", handleKeyDown); };
    }, [busy, onClose, open]);

    useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
    if (!open) return null;

    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!workspace || !name.trim() || !rule.id.trim()) { setError("Enter a policy name and rule identifier."); return; }
        if (rule.type === "REGEX" && !rule.pattern?.trim()) { setError("Regex rules require a pattern before publishing."); return; }
        setBusy(true);
        setError(null);
        try {
            const policy = await createGuardrailPolicy(workspace.id, name.trim(), description.trim());
            await createGuardrailVersion(policy.id, { rules: [{ ...rule, hooks: rule.type === "TOOL_POLICY" ? ["TOOL_INPUT"] : rule.hooks?.length ? rule.hooks : ["INPUT"] }] });
            onCreated(policy);
            setName("");
            setDescription("");
            setRule(newRule());
        } catch (reason: unknown) {
            setError(reason instanceof Error ? reason.message : "Unable to publish this policy version.");
        } finally { setBusy(false); }
    }

    function changeRuleType(type: GuardrailRule["type"]) {
        setRule((current) => ({ ...current, type, hooks: type === "TOOL_POLICY" ? ["TOOL_INPUT"] : current.hooks?.length ? current.hooks : ["INPUT"] }));
    }

    return (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
            <section className="modal-dialog guardrail-create-dialog" role="dialog" aria-modal="true" aria-labelledby="guardrail-dialog-title" aria-describedby="guardrail-dialog-description" ref={dialogRef} aria-busy={busy}>
                <div className="modal-heading">
                    <div><p className="panel-kicker">Workspace policy</p><h2 id="guardrail-dialog-title">Create custom policy</h2><p id="guardrail-dialog-description" className="panel-copy">Publish a structured rule set. Versions are immutable after publication.</p></div>
                    <button className="icon-button modal-close" type="button" onClick={onClose} disabled={busy} aria-label="Close create policy dialog"><X size={16} aria-hidden="true" /></button>
                </div>
                {error ? <div className="form-error guardrail-dialog-error" role="alert" tabIndex={-1} ref={errorRef}><AlertCircle size={15} aria-hidden="true" />{error}</div> : null}
                <form className="guardrail-dialog-form" onSubmit={(event) => void submit(event)}>
                    <div className="guardrail-form-grid"><label><span>Policy name <b aria-hidden="true">*</b></span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Outbound safety" required /></label><label><span>Description</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What does this policy protect?" rows={2} /></label></div>
                    <fieldset className="guardrail-rule-fieldset"><legend>First rule</legend>
                        <div className="guardrail-form-grid two-up"><label><span>Rule identifier <b aria-hidden="true">*</b></span><input value={rule.id} onChange={(event) => setRule({ ...rule, id: event.target.value })} required /></label><label><span>Rule type</span><select value={rule.type} onChange={(event) => changeRuleType(event.target.value as GuardrailRule["type"])}><option value="REGEX">Regex</option><option value="SECRET_DETECTION">Secret detection</option><option value="PII_REDACTION">PII redaction</option><option value="TOOL_POLICY">Tool policy</option><option value="MAX_PAYLOAD_SIZE">Maximum payload size</option></select></label></div>
                        <div className="guardrail-form-grid two-up"><label><span>Action</span><select value={rule.action} onChange={(event) => setRule({ ...rule, action: event.target.value as GuardrailRule["action"] })}><option value="BLOCK">Block</option><option value="REDACT">Redact</option><option value="REQUIRE_APPROVAL">Require approval · Phase 14</option></select></label>{rule.type === "REGEX" ? <label><span>Pattern</span><input value={rule.pattern ?? ""} onChange={(event) => setRule({ ...rule, pattern: event.target.value })} placeholder="forbidden phrase" /></label> : null}{rule.type === "MAX_PAYLOAD_SIZE" ? <label><span>Maximum bytes</span><input type="number" min={1} value={rule.max_bytes ?? 100000} onChange={(event) => setRule({ ...rule, max_bytes: Number(event.target.value) })} /></label> : null}{rule.type === "TOOL_POLICY" ? <label><span>Minimum risk</span><select value={rule.minimum_risk ?? "HIGH"} onChange={(event) => setRule({ ...rule, minimum_risk: event.target.value as GuardrailRule["minimum_risk"] })}><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option></select></label> : null}</div>
                        {rule.type === "TOOL_POLICY" ? <label className="guardrail-checkbox-row"><input type="checkbox" checked={rule.side_effect_only ?? true} onChange={(event) => setRule({ ...rule, side_effect_only: event.target.checked })} /><span>Side-effect tools only</span></label> : null}
                        {rule.type === "PII_REDACTION" ? <div className="guardrail-choice-group"><span className="guardrail-choice-label">PII classes</span><div>{(["EMAIL", "PHONE", "PAYMENT_CARD"] as const).map((entity) => <label className="guardrail-checkbox-row" key={entity}><input type="checkbox" checked={rule.entities?.includes(entity) ?? true} onChange={(event) => setRule({ ...rule, entities: event.target.checked ? [...(rule.entities ?? []), entity] : (rule.entities ?? []).filter((item) => item !== entity) })} /><span>{entity.replace("_", " ")}</span></label>)}</div></div> : null}
                        <div className="guardrail-choice-group"><span className="guardrail-choice-label">Run this rule at</span><div>{hooks.map((hook) => <label className="guardrail-checkbox-row" key={hook}><input type="checkbox" disabled={rule.type === "TOOL_POLICY" && hook !== "TOOL_INPUT"} checked={rule.hooks?.includes(hook) ?? false} onChange={(event) => setRule({ ...rule, hooks: event.target.checked ? [...(rule.hooks ?? []), hook] : (rule.hooks ?? []).filter((item) => item !== hook) })} /><span>{hookLabel(hook)}</span></label>)}</div></div>
                    </fieldset>
                    {rule.action === "REQUIRE_APPROVAL" ? <div className="guardrail-dialog-note"><SlidersHorizontal size={14} aria-hidden="true" /><span>Approval is fail-closed until Phase 14. It will not create a waiting run.</span></div> : null}
                    <div className="modal-actions"><button className="button secondary-button" type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="button primary-button" type="submit" disabled={busy || !workspace}>{busy ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}Publish policy</button></div>
                </form>
            </section>
        </div>
    );
}

export default function GuardrailsPage() {
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [policies, setPolicies] = useState<GuardrailPolicy[]>([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        async function loadWorkspace() {
            try {
                const response = await apiFetch("/v1/workspaces");
                if (!response.ok) throw new Error(await readApiError(response));
                const body = await response.json() as { data: Workspace[] };
                const saved = window.localStorage.getItem("vf-workspace-id");
                const selected = body.data.find((item) => item.id === saved) ?? body.data[0] ?? null;
                if (!cancelled) setWorkspace(selected);
            } catch (reason: unknown) { if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load workspaces."); }
        }
        void loadWorkspace();
        return () => { cancelled = true; };
    }, []);

    useEffect(() => {
        if (!workspace) { setLoading(false); return; }
        let cancelled = false;
        setLoading(true);
        void fetchGuardrails(workspace.id).then((items) => { if (!cancelled) setPolicies(items); }).catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load guardrails."); }).finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [workspace]);

    async function handleCreated(policy: GuardrailPolicy) {
        setDialogOpen(false);
        setMessage(`${policy.name} v1 published.`);
        if (workspace) setPolicies(await fetchGuardrails(workspace.id));
    }

    const activeBindings = policies.reduce((total, policy) => total + policy.usage_count, 0);

    return (
        <AppShell>
            <div className="guardrails-page">
                <header className="page-header guardrails-page-header"><div><p className="eyebrow">VibesFactory / Platform</p><h1>Guardrails</h1><p className="page-description">Versioned execution boundaries for untrusted input, model output, and tools.</p></div><div className="guardrails-header-actions"><span className="status-badge success"><span />Platform baseline v1</span><button className="button primary-button" type="button" onClick={() => { setError(null); setDialogOpen(true); }} disabled={!workspace}><Plus size={15} aria-hidden="true" />Create policy</button></div></header>
                {error ? <div className="form-error agent-alert" role="alert" tabIndex={-1}><AlertCircle size={15} aria-hidden="true" />{error}</div> : null}
                {message ? <div className="form-success agent-alert" role="status"><Check size={15} aria-hidden="true" />{message}</div> : null}
                {!loading && !workspace ? <section className="panel guardrails-empty-state"><ShieldCheck size={28} aria-hidden="true" /><h2>Create a workspace first</h2><p className="panel-copy">Guardrail policies are isolated by workspace.</p></section> : null}
                {workspace ? <>
                    <section className="guardrails-metrics" aria-label="Guardrail summary"><article className="metric-card panel metric-purple"><div className="metric-topline"><span className="metric-label">Policies</span><span className="metric-icon"><FileCode2 size={15} aria-hidden="true" /></span></div><strong className="metric-value">{policies.length + 1}</strong><span className="metric-footer">1 platform · {policies.length} custom</span></article><article className="metric-card panel metric-blue"><div className="metric-topline"><span className="metric-label">Active bindings</span><span className="metric-icon"><SlidersHorizontal size={15} aria-hidden="true" /></span></div><strong className="metric-value">{activeBindings}</strong><span className="metric-footer">Across published agents</span></article><article className="metric-card panel metric-green"><div className="metric-topline"><span className="metric-label">Coverage</span><span className="metric-icon"><ShieldCheck size={15} aria-hidden="true" /></span></div><strong className="metric-value">4</strong><span className="metric-footer">Runtime hook points</span></article></section>
                    <section className="panel guardrails-catalog-section" aria-labelledby="guardrails-catalog-title"><div className="panel-heading"><div><p className="panel-kicker">Workspace catalog</p><h2 id="guardrails-catalog-title">Policy library</h2></div><span className="code-hint">{workspace.name} · {policies.length + 1} policies</span></div>{loading ? <div className="guardrails-loading"><LoaderCircle className="spin" size={17} aria-hidden="true" />Loading policy library…</div> : <div className="guardrail-policy-grid"><BaselineCard />{policies.map((policy) => <PolicyCard key={policy.id} policy={policy} />)}</div>}</section>
                    <section className="panel guardrails-coverage-panel" aria-labelledby="guardrails-coverage-title"><div className="panel-heading"><div><p className="panel-kicker">Runtime coverage</p><h2 id="guardrails-coverage-title">Where guardrails run</h2></div><ShieldCheck size={18} aria-hidden="true" /></div><div className="guardrails-hook-grid">{hooks.map((hook, index) => <div className="guardrails-hook-card" key={hook}><span className="guardrail-hook-index">{String(index + 1).padStart(2, "0")}</span><div><strong>{hookLabel(hook)}</strong><small>{hook === "INPUT" ? "Before memory, retrieval, and model calls." : hook === "MODEL_OUTPUT" ? "Before text is persisted, reused, or streamed." : hook === "TOOL_INPUT" ? "Before credentials resolve or tools execute." : "Before tool output reaches traces or model context."}</small></div></div>)}</div></section>
                </> : null}
            </div>
            <GuardrailPolicyDialog open={dialogOpen} workspace={workspace} onClose={() => setDialogOpen(false)} onCreated={(policy) => void handleCreated(policy)} />
        </AppShell>
    );
}
