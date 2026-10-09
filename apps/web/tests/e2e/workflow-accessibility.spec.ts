import { expect, test } from "@playwright/test";

const workspaceId = "workspace-audit";
const workflowId = "workflow-audit";

test("workflow nodes can be selected, added, and connected without canvas dragging", async ({ page }) => {
  const workflow = {
    id: workflowId,
    workspace_id: workspaceId,
    name: "Accessibility workflow",
    slug: "accessibility-workflow",
    description: "Fixture for keyboard workflow controls.",
    status: "ACTIVE",
    latest_version_number: 1,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
  const definition = {
    schema_version: 1,
    configuration: {},
    nodes: [
      { key: "start", type: "START", name: "Start", config: {}, position: { x: 80, y: 100 } },
      { key: "agent", type: "AGENT", name: "Research", config: {}, position: { x: 360, y: 100 } },
      { key: "end", type: "END", name: "Finish", config: {}, position: { x: 640, y: 100 } },
    ],
    edges: [
      { source: "start", target: "agent" },
      { source: "agent", target: "end" },
    ],
  };

  await page.route("http://localhost:8000/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/v1/me") return route.fulfill({ json: { email: "audit@example.test" } });
    if (url.pathname === "/v1/workspaces") return route.fulfill({ json: { data: [{ id: workspaceId, name: "Audit workspace", role: "OWNER" }] } });
    if (url.pathname === `/v1/workflows/${workflowId}`) return route.fulfill({ json: workflow });
    if (url.pathname === `/v1/workflows/${workflowId}/draft`) return route.fulfill({ json: { workflow_id: workflowId, revision: 1, definition, updated_at: "2026-09-01T00:00:00Z" } });
    if (url.pathname === `/v1/workflows/${workflowId}/versions`) return route.fulfill({ json: { data: [{ id: "workflow-version-audit", version_number: 1 }] } });
    if (url.pathname === "/v1/workflow-versions/workflow-version-audit") return route.fulfill({ json: { id: "workflow-version-audit", workflow_id: workflowId, version_number: 1, configuration: { input_schema: { type: "object", properties: { topic: { type: "string", description: "The main topic needs to research", default: "Cloud computing" } }, required: ["topic"], additionalProperties: false } }, definition } });
    if (url.pathname === `/v1/workspaces/${workspaceId}/agents`) return route.fulfill({ json: { data: [] } });
    if (url.pathname === `/v1/workspaces/${workspaceId}/tools`) return route.fulfill({ json: { data: [] } });
    return route.fulfill({ status: 503, json: { detail: "No fixture for this request." } });
  });

  await page.goto(`/workflows/${workflowId}`);
  await expect(page.getByRole("heading", { name: "Accessibility workflow" })).toBeVisible();

  const nodeListDisclosure = page.getByText("Keyboard-accessible node list and connections");
  await nodeListDisclosure.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Workflow nodes" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Start: Start/ })).toHaveAttribute("aria-pressed", "false");

  const addCondition = page.locator(".workflow-palette").getByRole("button", { name: /Condition/ });
  await addCondition.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: /Condition: Condition/ })).toBeVisible();

  await page.getByLabel("Connection source node").selectOption({ label: "Condition: Condition" });
  await page.getByLabel("Connection source branch").selectOption("true");
  await page.getByLabel("Connection target node").selectOption("end");
  await page.getByRole("button", { name: "Connect nodes" }).click();
  await expect(page.getByRole("status").getByText("Connected Condition to Finish.")).toBeVisible();
});

test("workflow settings add input rows, space assistant fields, and keep the diagram reachable", async ({ page }) => {
  const workflow = {
    id: workflowId,
    workspace_id: workspaceId,
    name: "Settings workflow",
    slug: "settings-workflow",
    description: "Fixture for workflow editor settings.",
    status: "ACTIVE",
    latest_version_number: 1,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
  const definition = {
    schema_version: 1,
    configuration: {},
    nodes: [
      { key: "start", type: "START", name: "Start", config: {}, position: { x: 80, y: 100 } },
      { key: "end", type: "END", name: "Finish", config: {}, position: { x: 360, y: 100 } },
    ],
    edges: [{ source: "start", target: "end" }],
  };

  await page.route("http://localhost:8000/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/v1/me") return route.fulfill({ json: { email: "audit@example.test" } });
    if (url.pathname === "/v1/workspaces") return route.fulfill({ json: { data: [{ id: workspaceId, name: "Audit workspace", role: "OWNER" }] } });
    if (url.pathname === `/v1/workflows/${workflowId}`) return route.fulfill({ json: workflow });
    if (url.pathname === `/v1/workflows/${workflowId}/draft`) return route.fulfill({ json: { workflow_id: workflowId, revision: 1, definition, updated_at: "2026-09-01T00:00:00Z" } });
    if (url.pathname === `/v1/workflows/${workflowId}/versions`) return route.fulfill({ json: { data: [{ id: "workflow-version-audit", version_number: 1 }] } });
    if (url.pathname === "/v1/workflow-versions/workflow-version-audit") return route.fulfill({ json: { id: "workflow-version-audit", workflow_id: workflowId, version_number: 1, configuration: { input_schema: { type: "object", properties: { topic: { type: "string", description: "The main topic needs to research", default: "Cloud computing" } }, required: ["topic"], additionalProperties: false } }, definition } });
    if (url.pathname === `/v1/workspaces/${workspaceId}/agents`) return route.fulfill({ json: { data: [] } });
    if (url.pathname === `/v1/workspaces/${workspaceId}/tools`) return route.fulfill({ json: { data: [] } });
    return route.fulfill({ status: 503, json: { detail: "No fixture for this request." } });
  });

  await page.goto(`/workflows/${workflowId}`);
  await expect(page.getByRole("button", { name: "Chat" })).toBeVisible();
  const settingsPanels = page.locator("details.workflow-budget-settings");
  await settingsPanels.nth(0).locator("summary").click();
  await page.getByRole("button", { name: "Add input" }).click();
  const fieldName = page.getByLabel("Field 1 name");
  await expect(fieldName).toHaveValue("input_1");
  await fieldName.focus();
  await page.keyboard.press("End");
  await page.keyboard.type("x");
  await expect(fieldName).toHaveValue("input_1x");
  await expect(fieldName).toBeFocused();
  const fieldDescription = page.getByLabel("Field 1 description");
  await fieldDescription.focus();
  await page.keyboard.type("AI research");
  await expect(fieldDescription).toHaveValue("AI research");
  await expect(fieldDescription).toBeFocused();
  await fieldName.fill("");
  await expect(fieldName).toBeVisible();
  await expect(fieldName).toHaveValue("");
  await expect(settingsPanels.nth(0).locator("summary .workflow-panel-chevron")).toBeVisible();

  await settingsPanels.nth(1).locator("summary").click();
  await expect(page.locator(".workflow-chat-assistant-fields > label").first()).toHaveCSS("row-gap", "8px");

  await page.getByRole("button", { name: "Expand Run Settings" }).click();
  await expect(page.getByRole("button", { name: "Collapse Run Settings" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByLabel("Total tokens")).toBeVisible();
  const diagram = page.locator(".workflow-canvas-wrap");
  await diagram.scrollIntoViewIfNeeded();
  await expect(diagram).toBeInViewport();
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Open workflow diagram in full screen" }).click();
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(true);
  await expect(page.getByRole("button", { name: "Exit full screen workflow diagram" })).toBeVisible();
  await page.getByRole("button", { name: "Exit full screen workflow diagram" }).click();
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(false);

  for (const width of [768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const editorWidth = await page.locator(".workflow-editor-shell").evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }));
    expect(editorWidth.scrollWidth).toBeLessThanOrEqual(editorWidth.clientWidth);
  }

  await page.getByRole("button", { name: "Run", exact: true }).click();
  const runDialog = page.getByRole("dialog", { name: "Provide workflow input" });
  await expect(runDialog).toBeVisible();
  const inputRow = runDialog.locator(".workflow-input-row.is-schema-defined");
  await expect(inputRow.getByText("Field name")).toBeVisible();
  await expect(inputRow.locator(".workflow-input-field-key")).toContainText("topic");
  await expect(inputRow.locator(".workflow-input-field-key")).toContainText("Required");
  await expect(runDialog.getByLabel("topic value")).toHaveValue("Cloud computing");
  await expect(runDialog.getByText("The main topic needs to research")).toBeVisible();
  const gridColumns = await inputRow.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length);
  expect(gridColumns).toBe(2);
  const modalOverflow = await inputRow.evaluate((element) => element.scrollWidth - element.clientWidth);
  expect(modalOverflow).toBeLessThanOrEqual(0);
  const nameBox = await inputRow.locator(".workflow-input-field-key").boundingBox();
  const valueBox = await runDialog.getByLabel("topic value").boundingBox();
  expect(nameBox).not.toBeNull();
  expect(valueBox).not.toBeNull();
  expect(Math.abs(nameBox!.y - valueBox!.y)).toBeLessThanOrEqual(1);
});
