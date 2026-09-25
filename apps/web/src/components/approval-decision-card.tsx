"use client";

import { Check, Clock3, LoaderCircle, ShieldAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  FeedbackToast,
  type FeedbackToastState,
} from "./feedback-toast";
import {
  fetchApprovalRequest,
  resolveApproval,
  type Approval,
} from "../lib/approvals";

type Decision = "approve" | "reject";

function expiryLabel(expiresAt: string) {
  const remaining = new Date(expiresAt).getTime() - Date.now();
  if (remaining <= 0) return "Expired";
  const hours = Math.floor(remaining / 3_600_000);
  if (hours >= 24) return `${Math.floor(hours / 24)}d remaining`;
  if (hours > 0) return `${hours}h remaining`;
  return `${Math.max(1, Math.floor(remaining / 60_000))}m remaining`;
}

function statusClass(status: Approval["status"]) {
  if (status === "APPROVED") return "success";
  if (status === "REJECTED") return "error";
  if (status === "EXPIRED") return "muted";
  return "warning";
}

function DecisionDialog({
  approval,
  decision,
  busy,
  onCancel,
  onConfirm,
}: {
  approval: Approval;
  decision: Decision;
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
        aria-labelledby="inline-approval-dialog-heading"
        aria-describedby="inline-approval-dialog-copy"
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">Human review</span>
            <h2 id="inline-approval-dialog-heading">
              {approving ? "Approve this action?" : "Reject this action?"}
            </h2>
            <p className="panel-copy" id="inline-approval-dialog-copy">
              {approving
                ? "The action will run with the saved arguments shown below."
                : "The action will not run and this execution will stop."}
            </p>
          </div>
          <button
            className="icon-button modal-close"
            type="button"
            aria-label="Close confirmation"
            onClick={onCancel}
            disabled={busy}
          >
            <X size={17} aria-hidden="true" />
          </button>
        </div>
        <div className="approval-confirm-summary">
          <strong>{approval.requested_action}</strong>
          <pre>
            <code>{JSON.stringify(approval.arguments, null, 2)}</code>
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
            {busy ? "Saving decision…" : approving ? "Approve" : "Reject"}
          </button>
        </div>
      </section>
    </div>
  );
}

export function ApprovalDecisionCard({
  approvalId,
  onResolved,
}: {
  approvalId: string;
  onResolved?: (approval: Approval) => void;
}) {
  const [approval, setApproval] = useState<Approval | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<FeedbackToastState | null>(null);
  const notifiedStatus = useRef<Approval["status"] | null>(null);
  const onResolvedRef = useRef(onResolved);

  useEffect(() => {
    onResolvedRef.current = onResolved;
  }, [onResolved]);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const next = await fetchApprovalRequest(approvalId);
        if (cancelled) return;
        setApproval(next);
        setError(null);
        if (next.status !== "PENDING" && notifiedStatus.current !== next.status) {
          notifiedStatus.current = next.status;
          onResolvedRef.current?.(next);
        }
      } catch (reason: unknown) {
        if (!cancelled) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to load this approval request.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void refresh();
    const interval = window.setInterval(() => void refresh(), 4_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [approvalId]);

  async function submitDecision() {
    if (!approval || !decision || busy || approval.status !== "PENDING") return;
    setBusy(true);
    try {
      const resolved = await resolveApproval(approval.id, decision);
      setApproval(resolved);
      notifiedStatus.current = resolved.status;
      onResolvedRef.current?.(resolved);
      setDecision(null);
      setToast({
        kind: "success",
        message:
          decision === "approve"
            ? "Approved. Execution is resuming."
            : "Rejected. The execution will stop.",
      });
    } catch (reason: unknown) {
      setToast({
        kind: "error",
        message:
          reason instanceof Error ? reason.message : "Unable to save your decision.",
      });
      try {
        setApproval(await fetchApprovalRequest(approvalId));
      } catch {
        // Keep the existing request visible if the refresh also fails.
      }
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <section className="panel inline-approval-card" role="status">
        <LoaderCircle className="spin" size={17} aria-hidden="true" />
        Loading approval details…
      </section>
    );
  }

  if (error || !approval) {
    return (
      <section className="panel inline-approval-card inline-approval-error" role="alert">
        <ShieldAlert size={17} aria-hidden="true" />
        {error ?? "Approval request unavailable."}
      </section>
    );
  }

  const pending = approval.status === "PENDING";
  const statusCopy =
    approval.status === "APPROVED"
      ? "Approved · execution is resuming"
      : approval.status === "REJECTED"
        ? "Rejected · execution will stop"
        : approval.status === "EXPIRED"
          ? "Expired · action was not executed"
          : "This execution is paused until you decide.";

  return (
    <>
      <section
        className={`panel inline-approval-card${pending ? " is-pending" : " is-resolved"}`}
        aria-labelledby={`inline-approval-title-${approval.id}`}
      >
        <div className="inline-approval-heading">
          <span className="inline-approval-icon" aria-hidden="true">
            <ShieldAlert size={17} />
          </span>
          <div>
            <span className="panel-label">
              {approval.kind === "WORKFLOW_NODE"
                ? "Workflow approval required"
                : "Approval required"}
            </span>
            <h3 id={`inline-approval-title-${approval.id}`}>
              {approval.requested_action}
            </h3>
          </div>
          <span className={`status-badge ${statusClass(approval.status)}`}>
            {approval.status}
          </span>
        </div>

        <p className="inline-approval-copy">
          {pending ? "Paused here" : statusCopy}
          {pending ? <span> · {expiryLabel(approval.expires_at)}</span> : null}
        </p>
        <p className="inline-approval-risk">{approval.risk_reason}</p>

        <details className="inline-approval-arguments">
          <summary>Review saved arguments</summary>
          <pre>
            <code>{JSON.stringify(approval.arguments, null, 2)}</code>
          </pre>
        </details>

        {pending ? (
          <div className="inline-approval-actions">
            <button
              className="button primary-button"
              type="button"
              onClick={() => setDecision("approve")}
              disabled={busy}
            >
              <Check size={15} aria-hidden="true" />
              Approve
            </button>
            <button
              className="button danger-button"
              type="button"
              onClick={() => setDecision("reject")}
              disabled={busy}
            >
              <X size={15} aria-hidden="true" />
              Reject
            </button>
          </div>
        ) : (
          <div className="inline-approval-resolved" role="status">
            <Clock3 size={15} aria-hidden="true" />
            {statusCopy}
          </div>
        )}
      </section>
      {decision ? (
        <DecisionDialog
          approval={approval}
          decision={decision}
          busy={busy}
          onCancel={() => setDecision(null)}
          onConfirm={() => void submitDecision()}
        />
      ) : null}
      {toast ? <FeedbackToast toast={toast} onDismiss={() => setToast(null)} /> : null}
    </>
  );
}
