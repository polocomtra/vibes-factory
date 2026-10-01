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
