"use client";

import {
  ArrowUpRight,
  CalendarDays,
  CircleAlert,
  FlaskConical,
  LoaderCircle,
  Plus,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { AppShell } from "../../components/app-shell";
import { PrimaryTextArea, PrimaryTextInput } from "../../components/primary-text-field";
import { apiFetch, readApiError } from "../../lib/api";
import { createEvaluationDataset, fetchEvaluationDatasets, type EvaluationDataset } from "../../lib/evaluations";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };

function dateLabel(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently updated";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export default function EvaluationsPage() {
  const router = useRouter();
  const createTriggerRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const creatingRef = useRef(false);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setLoadError(null);
      try {
        const response = await apiFetch("/v1/workspaces");
        if (!response.ok) throw new Error(await readApiError(response));

        const body = await response.json() as { data: Workspace[] };
        const savedId = window.localStorage.getItem("vf-workspace-id");
        const selected = body.data.find((item) => item.id === savedId) ?? body.data[0] ?? null;
        if (cancelled) return;
        setWorkspace(selected);
        if (!selected) {
          setDatasets([]);
          return;
        }

        const items = await fetchEvaluationDatasets(selected.id);
        if (!cancelled) setDatasets(items);
      } catch (reason: unknown) {
        if (!cancelled) {
          const message = reason instanceof Error ? reason.message : "Unable to load evaluation datasets.";
          // The catalog's empty state is the useful fallback for a missing
          // evaluation collection on local API deployments.
          if (message.trim().toLowerCase() === "not found") {
            setDatasets([]);
            setLoadError(null);
          } else {
            setLoadError(message);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => { cancelled = true; };
  }, [reloadKey]);

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

  function openCreateDialog() {
    setCreateError(null);
    setMessage(null);
    setName("");
    setDescription("");
    setCreateOpen(true);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || creating || !name.trim()) return;

    creatingRef.current = true;
    setCreating(true);
    setCreateError(null);
    try {
      const dataset = await createEvaluationDataset(workspace.id, {
        name: name.trim(),
        description: description.trim(),
      });
      setDatasets((current) => [dataset, ...current]);
      setCreateOpen(false);
      setMessage(`“${dataset.name}” was created. Open it to add test cases.`);
    } catch (reason: unknown) {
      setCreateError(reason instanceof Error ? reason.message : "Unable to create dataset.");
    } finally {
      creatingRef.current = false;
      setCreating(false);
    }
  }

  return (
    <AppShell>
      <div className="page-content evaluation-page evaluation-catalog-page">
        <div className="page-header evaluation-page-header">
          <div>
            <p className="eyebrow">VibesFactory / Evaluate</p>
            <h1>Evaluations</h1>
            <p className="page-description">
              Build repeatable test suites and compare how your published agents perform.
            </p>
          </div>
          <button
            ref={createTriggerRef}
            className="button primary-button"
            type="button"
            aria-haspopup="dialog"
            aria-controls="evaluation-create-dialog"
            aria-expanded={createOpen}
            disabled={loading || !workspace}
            onClick={openCreateDialog}
          >
            <Plus size={16} aria-hidden="true" />
            Create dataset
          </button>
        </div>

        {loadError ? (
          <div className="form-error evaluation-feedback" role="alert" aria-live="polite">
            <CircleAlert size={16} aria-hidden="true" />
            <span><strong>Couldn’t load evaluation datasets.</strong> {loadError}</span>
            <button
              className="button secondary-button"
              type="button"
              onClick={() => setReloadKey((current) => current + 1)}
            >
              Try again
            </button>
          </div>
        ) : null}

        {message ? <p className="evaluation-message" role="status" aria-live="polite">{message}</p> : null}

        <section className="evaluation-catalog-section" aria-label="Evaluation datasets">
          {loading ? (
            <section className="panel agent-state evaluation-state" role="status">
              <LoaderCircle className="spin" size={18} aria-hidden="true" />
              Loading datasets…
            </section>
          ) : loadError ? null : !workspace ? (
            <section className="panel agent-empty-state evaluation-empty-state">
              <FlaskConical size={26} aria-hidden="true" />
              <h2>Create a workspace first</h2>
              <p className="panel-copy">Evaluation datasets belong to a workspace. Set one up in Settings to get started.</p>
            </section>
          ) : datasets.length === 0 ? (
            <section className="panel agent-empty-state evaluation-empty-state">
              <FlaskConical size={26} aria-hidden="true" />
              <h2>No evaluation datasets yet</h2>
              <p className="panel-copy">Your evaluation datasets will appear here once you create one.</p>
            </section>
          ) : (
            <div className="tools-card-grid evaluation-dataset-grid" aria-label="Evaluation datasets">
              {datasets.map((dataset) => (
                <article className="tool-agent-card evaluation-dataset-card" key={dataset.id}>
                  <button
                    className="tool-agent-card-main"
                    type="button"
                    aria-label={`Open ${dataset.name} evaluation dataset`}
                    onClick={() => router.push(`/evaluations/${dataset.id}`)}
                  >
                    <div className="tool-agent-card-top evaluation-dataset-card-top">
                      <span className="tool-agent-icon evaluation-dataset-icon">
                        <FlaskConical size={19} aria-hidden="true" />
                      </span>
                      <span className="status-badge info"><span aria-hidden="true" />Evaluation suite</span>
                    </div>
                    <div className="tool-agent-card-title evaluation-dataset-title">
                      <h2>{dataset.name}</h2>
                    </div>
                    <p>{dataset.description || "No description yet."}</p>
                    <div className="tool-agent-card-meta evaluation-dataset-meta">
                      <span>
                        <small>Test cases</small>
                        <b>{dataset.case_count} {dataset.case_count === 1 ? "case" : "cases"}</b>
                      </span>
                      <span>
                        <small>Last updated</small>
                        <b>{dateLabel(dataset.updated_at)}</b>
                      </span>
                    </div>
                  </button>
                  <footer className="evaluation-dataset-footer">
                    <span><CalendarDays size={14} aria-hidden="true" />Repeatable quality checks</span>
                    <span className="evaluation-open-label">Open dataset <ArrowUpRight size={15} aria-hidden="true" /></span>
                  </footer>
                </article>
              ))}
            </div>
          )}
        </section>

        {createOpen ? (
          <div
            className="modal-backdrop evaluation-modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !creating) setCreateOpen(false);
            }}
          >
            <section
              ref={dialogRef}
              id="evaluation-create-dialog"
              className="modal-dialog evaluation-create-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="evaluation-create-title"
              aria-describedby="evaluation-create-description"
              aria-busy={creating}
            >
              <header className="modal-heading">
                <div>
                  <p className="panel-kicker">Evaluation suite</p>
                  <h2 id="evaluation-create-title">Create dataset</h2>
                  <p id="evaluation-create-description" className="panel-copy">
                    Give your test suite a name. You can add cases and choose evaluators next.
                  </p>
                </div>
                <button
                  ref={closeButtonRef}
                  className="icon-button modal-close"
                  type="button"
                  aria-label="Close create dataset dialog"
                  disabled={creating}
                  onClick={() => setCreateOpen(false)}
                >
                  <X size={16} aria-hidden="true" />
                </button>
              </header>

              {createError ? <div className="form-error evaluation-modal-error" role="alert" aria-live="polite">{createError}</div> : null}

              <form className="modal-form evaluation-modal-form" onSubmit={(event) => void handleCreate(event)}>
                <label className="evaluation-modal-field" htmlFor="evaluation-dataset-name">
                  <span>Dataset name</span>
                  <PrimaryTextInput
                    id="evaluation-dataset-name"
                    value={name}
                    onChange={(event) => {
                      setName(event.target.value);
                      if (createError) setCreateError(null);
                    }}
                    maxLength={255}
                    required
                    autoComplete="off"
                    placeholder="Support regression suite"
                    disabled={creating}
                  />
                </label>
                <label className="evaluation-modal-field" htmlFor="evaluation-dataset-description">
                  <span>Description <em>(optional)</em></span>
                  <PrimaryTextArea
                    id="evaluation-dataset-description"
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    maxLength={10000}
                    rows={4}
                    placeholder="Core questions your agent should answer consistently."
                    disabled={creating}
                  />
                </label>
                <p className="field-helper">A dataset is a reusable collection of test cases for published agent versions.</p>
                <div className="modal-actions">
                  <button className="button secondary-button" type="button" disabled={creating} onClick={() => setCreateOpen(false)}>
                    Cancel
                  </button>
                  <button className="button primary-button" type="submit" disabled={creating || !name.trim()}>
                    {creating ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}
                    {creating ? "Creating…" : "Create dataset"}
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
