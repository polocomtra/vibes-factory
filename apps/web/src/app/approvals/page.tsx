"use client";

import {
  Check,
  Clock3,
  Code2,
  ExternalLink,
  LoaderCircle,
  ShieldAlert,
  X,
} from "lucide-react";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AppShell } from "../../components/app-shell";
import {
  FeedbackToast,
  type FeedbackToastState,
} from "../../components/feedback-toast";
import { apiFetch, readApiError } from "../../lib/api";
import { fetchRun } from "../../lib/runtime";
import {
  fetchApprovals,
  resolveApproval,
  type Approval,
} from "../../lib/approvals";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };
type ApprovalDecision = "approve" | "reject";

const statuses: Approval["status"][] = [
  "PENDING",
  "APPROVED",
  "REJECTED",
  "EXPIRED",
];

const kinds: Array<Approval["kind"] | "ALL"> = [
  "ALL",
  "TOOL_CALL",
  "WORKFLOW_NODE",
];

function formatRemaining(expiresAt: string) {
  const remaining = new Date(expiresAt).getTime() - Date.now();
  if (remaining <= 0) return "Expired";

  const hours = Math.floor(remaining / 3_600_000);
  if (hours >= 24) return `${Math.floor(hours / 24)}d remaining`;
  if (hours > 0) return `${hours}h remaining`;
  return `${Math.max(1, Math.floor(remaining / 60_000))}m remaining`;
}

function approvalStatusClass(status: Approval["status"]) {
  switch (status) {
    case "PENDING":
      return "warning";
    case "APPROVED":
      return "success";
    case "REJECTED":
      return "error";
    case "EXPIRED":
      return "muted";
  }
}

function ApprovalDialog({
  item,
  decision,
  busy,
  onCancel,
  onConfirm,
}: {
  item: Approval;
  decision: ApprovalDecision;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const approving = decision === "approve";

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="modal-dialog approval-confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="approval-confirm-heading"
        aria-describedby="approval-confirm-description"
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">Human review</span>
            <h2 id="approval-confirm-heading">
              {approving ? "Approve action?" : "Reject action?"}
            </h2>
            <p className="panel-copy" id="approval-confirm-description">
              {item.requested_action} will{" "}
              {approving
                ? "run with the exact arguments shown below."
                : "be blocked and the waiting run will stop."}
            </p>
          </div>
          <button
            className="icon-button modal-close"
            type="button"
            onClick={onCancel}
            disabled={busy}
            aria-label="Close approval dialog"
          >
            <X size={17} aria-hidden="true" />
          </button>
        </div>
        <div className="approval-confirm-summary">
          <strong>{item.requested_action}</strong>
          <pre>
            <code>{JSON.stringify(item.arguments, null, 2)}</code>
          </pre>
        </div>
        <div className="modal-actions">
          <button
            className="button subtle-button"
            type="button"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            className={`button ${approving ? "primary-button" : "danger-button"}`}
            type="button"
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? (
              <LoaderCircle className="spin" size={15} aria-hidden="true" />
            ) : approving ? (
              <Check size={15} aria-hidden="true" />
            ) : (
              <X size={15} aria-hidden="true" />
            )}
            {busy
              ? "Resolving…"
              : approving
                ? "Approve action"
                : "Reject action"}
          </button>
        </div>
      </section>
    </div>
  );
}

function ApprovalsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const requestedId = searchParams.get("request");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [items, setItems] = useState<Approval[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [filter, setFilter] = useState<Approval["status"]>("PENDING");
  const [kindFilter, setKindFilter] = useState<Approval["kind"] | "ALL">("ALL");
  const [selected, setSelected] = useState<Approval | null>(null);
  const [decision, setDecision] = useState<ApprovalDecision | null>(null);
  const [busy, setBusy] = useState(false);
  const [openingContext, setOpeningContext] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<FeedbackToastState | null>(null);

  useEffect(() => {
    let cancelled = false;

    void apiFetch("/v1/workspaces")
      .then(async (response) => {
        if (!response.ok) throw new Error(await readApiError(response));
        const body = (await response.json()) as { data: Workspace[] };
        const saved = window.localStorage.getItem("vf-workspace-id");
        const nextWorkspace =
          body.data.find((item) => item.id === saved) ?? body.data[0] ?? null;

        if (!cancelled) {
          setWorkspace(nextWorkspace);
          if (!nextWorkspace) setError("No workspace is available for this account.");
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(
            reason instanceof Error ? reason.message : "Unable to load workspaces.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!workspace) return;
    const workspaceId = workspace.id;
    let cancelled = false;

    async function refresh() {
      try {
        const [nextItems, pendingItems] = await Promise.all([
          fetchApprovals(
            workspaceId,
            filter,
            kindFilter === "ALL" ? undefined : kindFilter,
          ),
          fetchApprovals(workspaceId, "PENDING"),
        ]);
        if (cancelled) return;

        setItems(nextItems);
        setPendingCount(pendingItems.length);
        setSelected((current) => {
          const preferred = nextItems.find((item) => item.id === requestedId);
          return preferred ?? nextItems.find((item) => item.id === current?.id) ?? nextItems[0] ?? null;
        });
        setError(null);
      } catch (reason: unknown) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Unable to load approvals.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    setLoading(true);
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [workspace, filter, kindFilter, requestedId]);

  const pendingLabel = useMemo(
    () => `${pendingCount} pending approval${pendingCount === 1 ? "" : "s"}`,
    [pendingCount],
  );

  async function applyDecision() {
    if (!selected || !decision || busy) return;
    setBusy(true);
    try {
      const updated = await resolveApproval(selected.id, decision);
      setItems((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setSelected(updated);
      setPendingCount((count) => Math.max(0, count - 1));
      setFilter(updated.status);
      setDecision(null);
      setToast({
        kind: "success",
        message:
          decision === "approve"
            ? "Approval queued for execution."
            : "Approval rejected and run closed.",
      });
    } catch (reason: unknown) {
      setToast({
        kind: "error",
        message:
          reason instanceof Error ? reason.message : "Unable to resolve approval.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function openExecutionContext() {
    if (!selected || openingContext) return;
    if (selected.workflow_run_id) {
      router.push(`/workflow-runs/${selected.workflow_run_id}`);
      return;
    }
    if (!selected.run_id) return;

    setOpeningContext(true);
    try {
      const run = await fetchRun(selected.run_id);
      if (run.workflow_run_id) {
        router.push(`/workflow-runs/${run.workflow_run_id}`);
        return;
      }
      if (run.session_id) {
        const query = new URLSearchParams({
          session_id: run.session_id,
          run_id: run.id,
        });
        router.push(`/agents/${run.agent_id}/playground?${query.toString()}`);
      } else {
        setToast({
          kind: "error",
          message: "This run has no Playground session to open.",
        });
      }
    } catch (reason: unknown) {
      setToast({
        kind: "error",
        message:
          reason instanceof Error ? reason.message : "Unable to open the run.",
      });
    } finally {
      setOpeningContext(false);
    }
  }

  return (
    <AppShell>
      <div className="pagination-page approvals-page">
        <header className="page-header approvals-page-header">
          <div>
            <p className="eyebrow">VibesFactory / Platform</p>
            <h1>Approvals</h1>
            <p className="page-description">
              Review approval-sensitive actions before they run.
            </p>
          </div>
          <span className="status-badge warning approvals-pending-count">
            <ShieldAlert size={14} aria-hidden="true" />
            {pendingCount} pending
          </span>
        </header>

        <section className="panel approval-filters" aria-label="Approval filters">
          <div className="approval-filter-group" role="group" aria-label="Filter by status">
            <span className="approval-filter-label">Status</span>
            <div className="approval-filter-options">
              {statuses.map((status) => (
                <button
                  type="button"
                  key={status}
                  className={`button approval-filter-button ${filter === status ? "active" : ""}`}
                  aria-pressed={filter === status}
                  onClick={() => setFilter(status)}
                >
                  {status}
                </button>
              ))}
            </div>
          </div>
          <div className="approval-filter-group" role="group" aria-label="Filter by type">
            <span className="approval-filter-label">Type</span>
            <div className="approval-filter-options">
              {kinds.map((kind) => (
                <button
                  type="button"
                  key={kind}
                  className={`button approval-filter-button ${kindFilter === kind ? "active" : ""}`}
                  aria-pressed={kindFilter === kind}
                  onClick={() => setKindFilter(kind)}
                >
                  {kind === "ALL"
                    ? "All types"
                    : kind === "TOOL_CALL"
                      ? "Tools"
                      : "Workflows"}
                </button>
              ))}
            </div>
          </div>
        </section>

        {error ? (
          <div className="form-error agent-alert" role="alert">
            {error}
          </div>
        ) : null}

        {loading ? (
          <section className="panel agent-state approval-state" role="status">
            <LoaderCircle className="spin" size={18} aria-hidden="true" />
            Loading approvals…
          </section>
        ) : null}

        {!loading && !error && items.length === 0 ? (
          <section className="panel agent-empty-state approval-state">
            <ShieldAlert size={30} aria-hidden="true" />
            <h2>No {filter.toLowerCase()} approvals</h2>
            <p className="panel-copy">
              Matching approval requests will appear here.
            </p>
          </section>
        ) : null}

        {!loading && !error && items.length > 0 ? (
          <section className="approval-layout" aria-label="Approval requests">
            <ul className="approval-list" aria-label="Requests">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`approval-list-item ${selected?.id === item.id ? "selected" : ""}`}
                    aria-pressed={selected?.id === item.id}
                    onClick={() => setSelected(item)}
                  >
                    <span className="approval-item-icon" aria-hidden="true">
                      <Code2 size={16} />
                    </span>
                    <span className="approval-item-copy">
                      <strong>{item.requested_action}</strong>
                      <small>
                        {item.kind === "TOOL_CALL" ? "Tool call" : "Workflow checkpoint"}
                        <span aria-hidden="true"> · </span>
                        {new Date(item.requested_at).toLocaleString()}
                      </small>
                    </span>
                    <span className={`status-badge ${approvalStatusClass(item.status)}`}>
                      {item.status}
                    </span>
                  </button>
                </li>
              ))}
            </ul>

            {selected ? (
              <aside className="panel approval-detail" aria-labelledby="approval-detail-title">
                <div className="approval-detail-heading">
                  <div>
                    <span className="panel-label">Request detail</span>
                    <h2 id="approval-detail-title">{selected.requested_action}</h2>
                  </div>
                  <Clock3 size={18} aria-hidden="true" />
                </div>

                <dl className="approval-metadata">
                  <div>
                    <dt>Type</dt>
                    <dd>{selected.kind === "TOOL_CALL" ? "Tool call" : "Workflow"}</dd>
                  </div>
                  <div>
                    <dt>Risk reason</dt>
                    <dd>{selected.risk_reason}</dd>
                  </div>
                  <div>
                    <dt>Expires</dt>
                    <dd>{formatRemaining(selected.expires_at)}</dd>
                  </div>
                </dl>

                <section className="approval-arguments-section" aria-label="Requested arguments">
                  <div className="approval-arguments-heading">
                    <span>Arguments</span>
                    <span>Redacted view</span>
                  </div>
                  <pre className="approval-arguments">
                    <code>{JSON.stringify(selected.arguments, null, 2)}</code>
                  </pre>
                </section>

                {selected.status === "PENDING" ? (
                  <div className="approval-actions">
                    <button
                      className="button primary-button"
                      type="button"
                      onClick={() => setDecision("approve")}
                    >
                      <Check size={15} aria-hidden="true" />
                      Approve
                    </button>
                    <button
                      className="button danger-button"
                      type="button"
                      onClick={() => setDecision("reject")}
                    >
                      <X size={15} aria-hidden="true" />
                      Reject
                    </button>
                  </div>
                ) : (
                  <div className="approval-resolved-note">
                    <span className={`status-badge ${approvalStatusClass(selected.status)}`}>
                      {selected.status}
                    </span>
                    <span role="status" aria-live="polite" aria-atomic="true">
                      {selected.resolved_at
                        ? `Resolved ${new Date(selected.resolved_at).toLocaleString()}`
                        : "This request is no longer pending."}
                    </span>
                    <button
                      className="button subtle-button approval-open-context"
                      type="button"
                      onClick={() => void openExecutionContext()}
                      disabled={openingContext}
                    >
                      {openingContext ? (
                        <LoaderCircle className="spin" size={15} aria-hidden="true" />
                      ) : (
                        <ExternalLink size={15} aria-hidden="true" />
                      )}
                      {openingContext
                        ? "Opening…"
                        : selected.workflow_run_id
                          ? "Open workflow run"
                          : "Open session"}
                    </button>
                  </div>
                )}
              </aside>
            ) : null}
          </section>
        ) : null}

        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {pendingLabel}
        </div>
        {decision && selected ? (
          <ApprovalDialog
            item={selected}
            decision={decision}
            busy={busy}
            onCancel={() => setDecision(null)}
            onConfirm={() => void applyDecision()}
          />
        ) : null}
        {toast ? <FeedbackToast toast={toast} onDismiss={() => setToast(null)} /> : null}
      </div>
    </AppShell>
  );
}

export default function ApprovalsPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <section className="panel agent-state approval-state" role="status">
            <LoaderCircle className="spin" size={18} aria-hidden="true" />
            Loading approvals…
          </section>
        </AppShell>
      }
    >
      <ApprovalsContent />
    </Suspense>
  );
}
