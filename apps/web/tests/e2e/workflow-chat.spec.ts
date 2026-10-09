import { expect, test } from "@playwright/test";

const workflowId = "workflow-chat-audit";
const versionId = "workflow-chat-version";
const chatId = "workflow-chat-session";
const runId = "workflow-chat-run";
const workspaceId = "workspace-chat-audit";

const workflow = {
  id: workflowId,
  workspace_id: workspaceId,
  name: "Research workflow",
  slug: "research-workflow",
  description: "Research a topic and return findings.",
  status: "ACTIVE",
  latest_version_number: 1,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
};
const definition = {
  schema_version: 1,
  configuration: {
    input_schema: {
      type: "object",
      properties: { topic: { type: "string", description: "Research subject" } },
      required: ["topic"],
      additionalProperties: false,
    },
    chat: { enabled: true, description: "Research a topic and return findings." },
  },
  nodes: [
    { key: "start", type: "START", name: "Start", config: {}, position: { x: 40, y: 80 } },
    { key: "research", type: "AGENT", name: "Research agent", config: {}, position: { x: 280, y: 80 } },
    { key: "finish", type: "END", name: "Finish", config: {}, position: { x: 520, y: 80 } },
  ],
  edges: [{ source: "start", target: "research" }, { source: "research", target: "finish" }],
};

function session() {
  return {
    id: chatId,
    workflow_id: workflowId,
    workflow_version_id: versionId,
    title: "Research workflow",
    collected_input: { topic: "AI orchestration frameworks" },
    active_run_id: runId,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
  };
}

function run(status: "RUNNING" | "COMPLETED" = "RUNNING") {
  return {
    id: runId,
    workflow_id: workflowId,
    workflow_version_id: versionId,
    trace_id: "trace-chat-audit",
    status,
    current_node_key: status === "RUNNING" ? "research" : null,
    current_node_name: status === "RUNNING" ? "Research agent" : null,
    input: { topic: "AI orchestration frameworks" },
    variables: {},
    node_outputs: {},
    output: status === "COMPLETED" ? { markdown: "## Findings\n\nPython frameworks include LangGraph and LlamaIndex." } : null,
    usage: {},
    execution_budget: {},
    error: null,
    started_at: "2026-10-01T00:01:00Z",
    completed_at: status === "COMPLETED" ? "2026-10-01T00:02:00Z" : null,
    created_at: "2026-10-01T00:00:00Z",
  };
}

test("workflow chat collects intent, queues a run, and renders its output", async ({ page }) => {
  const transcript: Array<Record<string, unknown>> = [];
  let turnCount = 0;
  let currentRunStatus: "RUNNING" | "COMPLETED" = "RUNNING";

  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/v1/me") return route.fulfill({ json: { email: "chat@example.test" } });
    if (path === "/v1/workspaces") return route.fulfill({ json: { data: [{ id: workspaceId, name: "Chat workspace", role: "OWNER" }] } });
    if (path === `/v1/workflows/${workflowId}`) return route.fulfill({ json: workflow });
    if (path === `/v1/workflows/${workflowId}/versions`) return route.fulfill({ json: { data: [{ id: versionId, version_number: 1, configuration: definition.configuration }] } });
    if (path === `/v1/workflows/${workflowId}/chats`) return route.fulfill({ json: { data: [session()] } });
    if (path === `/v1/workflow-chats/${chatId}`) return route.fulfill({ json: session() });
    if (path === `/v1/workflow-chats/${chatId}/messages`) return route.fulfill({ json: { data: transcript, pagination: { next_cursor: null, has_more: false } } });
    if (path === `/v1/workflow-versions/${versionId}`) return route.fulfill({ json: { id: versionId, workflow_id: workflowId, version_number: 1, configuration: definition.configuration, definition } });
    if (path === `/v1/workflow-runs/${runId}`) return route.fulfill({ json: run(currentRunStatus) });
    if (path === `/v1/workflow-runs/${runId}/nodes`) {
      return route.fulfill({
        json: {
          data: [{
            id: "node-run-research",
            node_key: "research",
            node_name: "Research agent",
            node_type: "AGENT",
            status: currentRunStatus,
            attempt: 1,
            input: {},
            output: null,
            error: null,
            agent_run_id: null,
            span_id: null,
            usage: {},
            duration_ms: null,
            started_at: "2026-10-01T00:01:00Z",
            completed_at: null,
          }],
          pagination: { next_cursor: null, has_more: false },
        },
      });
    }
    if (path === `/v1/workflow-runs/${runId}/events`) {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `id: 1\nevent: WORKFLOW_QUEUED\ndata: ${JSON.stringify({ sequence: 1, event: "WORKFLOW_QUEUED", workflow_run_id: runId, node_run_id: "node-run-research", occurred_at: "2026-10-01T00:00:00Z", data: { source: "chat", node_name: "Research agent" } })}\n\n`,
      });
    }
    if (path === `/v1/runs/${runId}/children`) return route.fulfill({ json: { data: [], pagination: { next_cursor: null, has_more: false } } });
    if (path === `/v1/workflow-chats/${chatId}/turns` && request.method() === "POST") {
      const body = request.postDataJSON() as { message: string };
      turnCount += 1;
      const turnId = `turn-${turnCount}`;
      transcript.push({ id: `user-${turnCount}`, sequence_no: turnCount * 2 - 1, role: "USER", kind: "TEXT", content: { text: body.message }, workflow_run_id: null, created_at: new Date().toISOString() });
      if (turnCount === 1) {
        transcript.push({ id: "assistant-1", sequence_no: 2, role: "ASSISTANT", kind: "TEXT", content: { text: "Which language should I prioritize?" }, workflow_run_id: null, created_at: new Date().toISOString() });
      } else {
        transcript.push({ id: "assistant-2", sequence_no: 4, role: "ASSISTANT", kind: "WORKFLOW_RUN", content: { input: { topic: "AI orchestration frameworks for Python" }, text: "Starting the research workflow." }, workflow_run_id: runId, created_at: new Date().toISOString() });
      }
      return route.fulfill({ status: 202, json: { id: turnId, chat_session_id: chatId, status: "COMPLETED", decision: { action: turnCount === 1 ? "ask" : "run", reply: "", input: {} }, error: null, workflow_run_id: turnCount > 1 ? runId : null, trace_id: null, created_at: new Date().toISOString(), completed_at: new Date().toISOString() } });
    }
    if (path.startsWith("/v1/workflow-chat-turns/")) return route.fulfill({ json: { id: path.split("/").at(-1), chat_session_id: chatId, status: "COMPLETED", decision: { action: "answer", reply: "", input: {} }, error: null, workflow_run_id: turnCount > 1 ? runId : null, trace_id: null, created_at: new Date().toISOString(), completed_at: new Date().toISOString() } });
    return route.fulfill({ status: 503, json: { detail: `No fixture for ${path}` } });
  });

  await page.goto(`/workflows/${workflowId}/chat?chatId=${chatId}`);
  await expect(page.getByRole("heading", { name: "Research workflow" })).toBeVisible();
  const composer = page.getByLabel("Message the workflow assistant");
  await composer.fill("Research AI orchestration frameworks");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Which language should I prioritize?")).toBeVisible({ timeout: 5000 });

  await composer.fill("Run it for Python");
  await page.getByRole("button", { name: "Send" }).click();
  const conversation = page.getByRole("region", { name: "Workflow conversation" });
  const execution = page.getByRole("region", { name: "Workflow execution" });
  await expect(conversation.getByText("Workflow run", { exact: true })).toBeVisible({ timeout: 5000 });
  await expect(execution.getByText("Research agent").first()).toBeVisible();
  await page.getByText("Keyboard accessible workflow nodes").click();
  await execution.getByRole("button", { name: "Research agent AGENT" }).click();
  await expect(execution.getByRole("button", { name: "Clear node filter" })).toBeVisible();
  await execution.getByRole("button", { name: "Clear node filter" }).click();
  await execution.getByRole("button", { name: "Inspect Research agent trace" }).click();
  await expect(execution.getByRole("button", { name: "Clear node filter" })).toBeVisible();
  await execution.getByRole("button", { name: "Clear node filter" }).click();

  currentRunStatus = "COMPLETED";
  await expect(conversation.getByText("LangGraph and LlamaIndex")).toBeVisible({ timeout: 5000 });
  await expect(page.getByRole("button", { name: "New activity · scroll to latest" })).toBeHidden();
  await expect(execution.locator(".workflow-run-summary")).toContainText("COMPLETED", { timeout: 5000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "test-results/workflow-chat-desktop.png" });
  await page.getByRole("button", { name: "Change appearance" }).click();
  await page.getByRole("menuitemradio", { name: "Light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({ path: "test-results/workflow-chat-light.png" });
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole("tab", { name: "Execution" })).toBeVisible();
  await page.getByRole("tab", { name: "Execution" }).click();
  await expect(execution).toBeVisible();
  await page.screenshot({ path: "test-results/workflow-chat-mobile-execution.png" });
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflows, `unexpected horizontal overflow at ${width}px`).toBe(false);
  }
});
