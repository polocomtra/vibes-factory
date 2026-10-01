"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info, X } from "lucide-react";
import { usePathname } from "next/navigation";

export type FeatureHelpId =
  | "dashboard" | "agents" | "agent-overview" | "agent-instructions" | "agent-model"
  | "agent-tools" | "agent-knowledge" | "agent-memory" | "agent-guardrails" | "agent-delegation"
  | "agent-versions" | "playground" | "workflows" | "workflow-runs" | "tools" | "knowledge"
  | "memory" | "mcp" | "guardrails" | "approvals" | "deployments" | "traces" | "monitoring"
  | "evaluations" | "settings" | "settings-members" | "settings-model" | "settings-credentials" | "login";

type FeatureGuide = {
  title: string;
  whatItIs: string;
  howItWorks: string[];
};

const guide = (title: string, whatItIs: string, howItWorks: string[]): FeatureGuide => ({ title, whatItIs, howItWorks });

export const featureGuides: Record<FeatureHelpId, FeatureGuide> = {
  dashboard: guide("Dashboard", "The Dashboard summarizes recent agent and workflow activity for the selected workspace. It brings run volume, success rate, latency, and estimated cost together so you can spot changes quickly.", ["Choose a workspace from the sidebar.", "Review the default seven-day activity summary.", "Open Monitoring to adjust the time range and inspect more detailed metrics."]),
  agents: guide("Agents", "Agents combine instructions, a model, and optional capabilities such as tools, knowledge, memory, and guardrails. You can test a draft, then publish an immutable version for deployments and runs to use.", ["Create an agent and give it a name and description.", "Configure its instructions, model, and capabilities in the sections on the left.", "Save the draft, test it in Playground, then publish when ready."]),
  "agent-overview": guide("Agent overview", "Overview stores an agent's name, slug, and description. These details identify the agent in catalogs and traces without changing its published runtime version.", ["Edit the name or description.", "Save details to apply metadata changes.", "Use Save draft and Publish for versioned runtime configuration."]),
  "agent-instructions": guide("Instructions", "Instructions define the role, goals, and behavioral boundaries the agent should follow. They are included in the agent's runtime configuration when a new version is published.", ["Describe the task and expected outcome.", "Add constraints, response style, and what to do when information is missing.", "Save the draft and test representative prompts in Playground."]),
  "agent-model": guide("Model and execution", "This section selects the model that generates the agent's responses and controls the execution limits available to it. The configured budgets bound a run; they do not guarantee a specific provider cost.", ["Choose a model configured for this workspace.", "Set the available generation and runtime limits.", "Save the draft and test its responses before publishing."]),
  "agent-tools": guide("Agent tools", "Tools give an agent specific actions, such as calling an integration or using a built-in capability. The agent can use only tools that are attached to its configuration.", ["Review a tool's description and input schema.", "Attach the tools this agent needs and configure required credentials.", "Save and test tool calls in Playground before publishing."]),
  "agent-knowledge": guide("Agent knowledge", "Knowledge connects an agent to curated documents such as manuals, policies, and product guides. The agent can retrieve relevant passages from processed sources and use them to ground answers.", ["Upload documents to a knowledge base.", "Wait for each document to finish processing.", "Attach a ready knowledge base to this agent and verify citations in Playground."]),
  "agent-memory": guide("Agent memory", "Memory provides an agent with scoped information to retain across interactions, such as user preferences, procedures, or recurring context. Unlike Knowledge, it stores records about ongoing use rather than curated reference documents.", ["Choose the memory store available to this agent.", "Configure the supported memory types and scope.", "Test what the agent can retrieve or update in Playground."]),
  "agent-guardrails": guide("Agent guardrails", "Guardrails apply workspace policies to supported points in an agent run. Depending on the policy, they can allow an action, block it, or pause it for approval.", ["Select the policies this agent should use.", "Review each policy's checkpoint and enforcement action.", "Save the draft, then inspect blocks or approval requests in run details."]),
  "agent-delegation": guide("Delegated agents", "Delegation lets an agent hand a bounded task to another configured agent. The parent can use only child agents explicitly allowed in this section.", ["Choose an available child agent.", "Describe the task or handoff context it should receive.", "Test the parent agent and inspect child runs in Traces."]),
  "agent-versions": guide("Agent versions", "Versions are the saved, published snapshots of an agent's runtime configuration. A published version is immutable so existing runs and deployments can continue using the configuration they were assigned.", ["Review the versions and their published status.", "Save and publish a draft to create a new version.", "Pin deployments to the version they should run."]),
  playground: guide("Playground", "Playground is an interactive space to test an agent version without changing its deployment. Each message creates a run in a session, where you can review streaming output and tool activity.", ["Select an agent and the version to test.", "Start a session or continue an existing one, then send a message.", "Inspect the response, tool calls, usage, and trace before changing the draft."]),
  workflows: guide("Workflows", "A workflow connects supported steps into a repeatable execution graph. It can coordinate agents and tools, transform data, evaluate conditions, and pause for an approval where configured.", ["Create a workflow and open its editor.", "Add nodes, connect them, and resolve validation messages.", "Save or publish the graph, then run it and review its history."]),
  "workflow-runs": guide("Workflow run history", "Run history lists previous executions of a workflow and their final or waiting status. Opening a run shows its nodes, outputs, usage, and any approval that paused execution.", ["Choose a workflow run from the history list.", "Review its status, timing, and current or completed node.", "Open the run details to inspect node results or handle a pending approval."]),
  tools: guide("Tools", "The Tools catalog contains built-in and connected actions that agents can call. Each tool definition describes its inputs and any configuration or credentials needed to execute it.", ["Search or filter the catalog by tool type.", "Open a tool and review its schema and configuration.", "Attach it to an agent or workflow where it is needed."]),
  knowledge: guide("Knowledge", "Knowledge bases organize documents that agents can search for relevant reference information. Uploaded files are processed into searchable content before they can reliably ground a response.", ["Create or open a knowledge base.", "Upload supported documents and check their processing status.", "Attach a ready base to an agent and verify retrieved citations."]),
  memory: guide("Memory", "Memory stores scoped records that help an agent retain useful context across interactions, such as preferences, procedures, or recurring facts. It differs from Knowledge, which contains curated source documents for reference.", ["Create or select a memory store.", "Choose the available type or agent scope to narrow records.", "Search for related memories and review the results before relying on them."]),
  mcp: guide("MCP servers", "An MCP server exposes tools through the Model Context Protocol so VibesFactory can discover and import them. Importing a tool adds its definition to the workspace; it does not automatically enable it for every agent.", ["Add the MCP server URL and any required authentication.", "Test the connection, then discover the server's tools.", "Import the tools you need and attach them to an agent."]),
  guardrails: guide("Guardrails", "Guardrails define policies that inspect supported runtime checkpoints, such as incoming input or tool activity. A policy can allow, block, or require an authorized approval before a run continues.", ["Create a policy and choose its checkpoint.", "Set its rule and enforcement action.", "Attach the policy to an agent, then review its decisions in run activity."]),
  approvals: guide("Approvals", "Approvals are requests to review an operation that a policy has paused. The request includes its reason, risk, expiry, and available redacted context so an authorized person can decide whether the run may continue.", ["Open a pending approval and review its reason and scope.", "Check the risk, expiry, and redacted arguments.", "Approve or reject once, then inspect the run's resulting status."]),
  deployments: guide("Deployments", "A deployment exposes a pinned agent version through an authenticated runtime endpoint. API keys authorize callers, while sessions can carry a conversation across runs and streaming can return events as a run progresses.", ["Create a deployment for the intended agent version.", "Create an API key and keep its raw value in a server-side secret store.", "Call the endpoint from your service and use the returned session ID to continue a conversation."]),
  traces: guide("Traces", "Traces show runtime activity across all workspaces your account can access. They organize sessions, runs, and spans so you can inspect execution flow, errors, redacted payloads, and usage.", ["Search or filter the trace list to find a session or run.", "Open a trace and follow its tree or timeline.", "Inspect inputs, outputs, attributes, errors, and usage; sensitive payloads may be redacted."]),
  monitoring: guide("Monitoring", "Monitoring aggregates run reliability, latency, volume, and estimated model cost for a selected workspace and time range. It helps reveal operational trends; incomplete or missing data should not be read as zero.", ["Choose a workspace and time range.", "Apply the filters relevant to the question you're investigating.", "Review the summary, charts, and accessible data table together."]),
  evaluations: guide("Evaluations", "Evaluations run configured checks against dataset cases and a selected agent version. Results help compare response quality across compatible runs without changing the deployed version.", ["Review the dataset cases and evaluator settings.", "Choose the agent version to evaluate.", "Run the evaluation and inspect scores or a compatible comparison."]),
  settings: guide("Workspace settings", "Workspace settings control membership, model connections, and integration credential metadata. Available actions depend on your workspace role and keep secret values hidden after their supported entry or creation flow.", ["Choose the settings section you need.", "Review the workspace scope and the effect of the change.", "Test model connections or manage credentials using the available controls."]),
  "settings-members": guide("Workspace members", "The member list shows who can access the selected workspace and which role they hold. Roles determine which workspace actions each person is allowed to perform.", ["Confirm the selected workspace.", "Find a member and review their assigned role.", "Use the available membership controls if your role allows a change."]),
  "settings-model": guide("Model connections", "Model connections configure provider access that agents can use in this workspace. Testing a connection checks whether the supplied configuration can reach the provider.", ["Choose the provider and model details.", "Enter the required connection information.", "Run the connection test and review its result before using the model in an agent."]),
  "settings-credentials": guide("Credentials", "Credentials are protected values used by integrations, tools, and deployments. This section manages their lifecycle and shows metadata without exposing stored secrets again.", ["Identify the credential and the integrations that use it.", "Create, rotate, or revoke it with the available action.", "Update dependent integrations after a credential change."]),
  login: guide("Sign in", "Sign in to verify your account and open the VibesFactory workspaces you can access. The console loads workspace data only after your session is authenticated.", ["Enter the email address and password for your account.", "Submit the form and read any validation message.", "After sign-in, choose the workspace you want to work in."]),
};

export function FeatureHelpButton({ id }: { id: FeatureHelpId }) {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const content = featureGuides[id];

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) dialog.close();
  }, [open]);

  return <>
    <button className="feature-help-trigger" type="button" aria-label={`How ${content.title} works`} title={`How ${content.title} works`} onClick={() => setOpen(true)}><Info size={16} aria-hidden="true" /></button>
    <dialog ref={dialogRef} className="feature-help-dialog" aria-labelledby={`feature-help-${id}-title`} onClose={() => setOpen(false)}>
      <header className="feature-help-header"><div><p className="eyebrow">FEATURE GUIDE</p><h2 id={`feature-help-${id}-title`}>{content.title}</h2></div><button className="icon-button modal-close" type="button" aria-label="Close guide" onClick={() => setOpen(false)}><X size={17} aria-hidden="true" /></button></header>
      <div className="feature-help-body">
        <section><h3>What it is?</h3><p>{content.whatItIs}</p></section>
        <section><h3>How it works</h3><ul>{content.howItWorks.map((step) => <li key={step}>{step}</li>)}</ul></section>
      </div>
      <footer className="feature-help-footer"><button className="button secondary-button" type="button" onClick={() => setOpen(false)}>Close</button></footer>
    </dialog>
  </>;
}

const routeHelp: Array<{ match: (path: string) => boolean; id: FeatureHelpId }> = [
  { match: (path) => path === "/", id: "dashboard" }, { match: (path) => path.startsWith("/agents/") && !path.includes("/playground"), id: "agents" },
  { match: (path) => path === "/agents", id: "agents" }, { match: (path) => path.includes("/playground"), id: "playground" },
  { match: (path) => path.startsWith("/workflows/") || path.startsWith("/workflow-runs/"), id: "workflow-runs" },
  { match: (path) => path === "/workflows", id: "workflows" }, { match: (path) => path.startsWith("/tools"), id: "tools" },
  { match: (path) => path.startsWith("/knowledge"), id: "knowledge" }, { match: (path) => path.startsWith("/memory"), id: "memory" },
  { match: (path) => path.startsWith("/mcp-servers"), id: "mcp" }, { match: (path) => path.startsWith("/guardrails"), id: "guardrails" },
  { match: (path) => path.startsWith("/approvals"), id: "approvals" }, { match: (path) => path.startsWith("/deployments"), id: "deployments" },
  { match: (path) => path.startsWith("/traces"), id: "traces" }, { match: (path) => path.startsWith("/monitoring"), id: "monitoring" },
  { match: (path) => path.startsWith("/evaluations"), id: "evaluations" }, { match: (path) => path.startsWith("/settings"), id: "settings" },
];

export function RouteFeatureHelp() {
  const pathname = usePathname();
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [agentSection, setAgentSection] = useState<FeatureHelpId | null>(null);
  const routeId = useMemo(() => routeHelp.find((route) => route.match(pathname))?.id, [pathname]);
  const id = agentSection ?? routeId;

  useEffect(() => {
    const sectionIds: Record<string, FeatureHelpId> = {
      overview: "agent-overview", configuration: "agent-overview", instructions: "agent-instructions",
      model: "agent-model", tools: "agent-tools", knowledge: "agent-knowledge", memory: "agent-memory",
      guardrails: "agent-guardrails", agents: "agent-delegation", delegation: "agent-delegation", versions: "agent-versions",
    };
    const settingsIds: Record<string, FeatureHelpId> = { workspace: "settings", members: "settings-members", "model-test": "settings-model", credentials: "settings-credentials" };
    const isAgent = pathname.startsWith("/agents/") && !pathname.includes("/playground");
    const isSettings = pathname.startsWith("/settings");
    if (!isAgent && !isSettings) { setAgentSection(null); return; }
    const readSection = () => {
      const section = new URLSearchParams(window.location.search).get("tab");
      setAgentSection(isAgent ? (section ? sectionIds[section] ?? "agent-overview" : "agent-overview") : (section ? settingsIds[section] ?? "settings" : "settings"));
    };
    readSection();
    const onPopState = () => {
      readSection();
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [pathname]);

  useEffect(() => {
    if (!id) { setHost(null); return; }
    let container: HTMLSpanElement | null = null;
    const attach = () => {
      if (container?.isConnected) return true;
      const title = document.querySelector<HTMLElement>(".content-frame h1, .content-frame .page-header h1");
      if (!title) return false;
      container = document.createElement("span");
      container.className = "feature-help-slot";
      title.after(container);
      setHost(container);
      return true;
    };
    const observer = new MutationObserver(() => { if (attach()) observer.disconnect(); });
    if (!attach()) observer.observe(document.querySelector(".content-frame") ?? document.body, { childList: true, subtree: true });
    return () => { observer.disconnect(); container?.remove(); };
  }, [id, pathname]);

  return host && id ? createPortal(<FeatureHelpButton id={id} />, host) : null;
}
