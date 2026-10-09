import { expect, test } from "@playwright/test";

const workspaceId = "workflow-create-workspace";

test("workflow creation modal uses theme surfaces and fits a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 844 });
  await page.route("http://localhost:8000/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/v1/me") return route.fulfill({ json: { email: "create@example.test" } });
    if (url.pathname === "/v1/workspaces") return route.fulfill({ json: { data: [{ id: workspaceId, name: "Create workspace", role: "OWNER" }] } });
    if (url.pathname === `/v1/workspaces/${workspaceId}/workflows`) return route.fulfill({ json: { data: [] } });
    return route.fulfill({ status: 503, json: { detail: "No fixture for this request." } });
  });

  await page.goto("/workflows");
  await page.getByRole("button", { name: "New workflow" }).click();

  const dialog = page.getByRole("dialog", { name: "Create a workflow" });
  await expect(dialog).toBeVisible();
  const nameBackground = await page.getByLabel("Workflow name").evaluate((element) => getComputedStyle(element).backgroundColor);
  const descriptionBackground = await page.getByLabel("Description (optional)").evaluate((element) => getComputedStyle(element).backgroundColor);
  const cancelBackground = await dialog.getByRole("button", { name: "Cancel" }).evaluate((element) => getComputedStyle(element).backgroundColor);
  expect(nameBackground).not.toBe("rgb(255, 255, 255)");
  expect(descriptionBackground).not.toBe("rgb(255, 255, 255)");
  expect(cancelBackground).not.toBe("rgb(255, 255, 255)");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
});
