import { expect, test } from "@playwright/test";

const routes = [
  "/",
  "/agents",
  "/agents/new",
  "/agents/visual-audit",
  "/approvals",
  "/deployments",
  "/deployments/visual-audit",
  "/evaluations",
  "/evaluations/visual-audit",
  "/guardrails",
  "/knowledge",
  "/knowledge/visual-audit",
  "/login",
  "/mcp-servers",
  "/mcp-servers/visual-audit",
  "/memory",
  "/memory/visual-audit",
  "/monitoring",
  "/playground",
  "/settings",
  "/tools",
  "/traces",
  "/traces/visual-audit",
  "/workflow-runs/visual-audit",
  "/workflows",
  "/workflows/visual-audit",
  "/workflows/visual-audit/runs",
];

const viewports = [375, 390, 768, 1024, 1440];

test("existing routes reflow without page-level horizontal overflow in both themes", async ({ browser }) => {
  test.setTimeout(240_000);
  const overflow: Array<{ route: string; theme: string; width: number; scrollWidth: number }> = [];

  for (const theme of ["dark", "light"] as const) {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    await context.addInitScript((value) => localStorage.setItem("vf-theme", value), theme);
    const page = await context.newPage();
    await page.route("http://localhost:8000/**", (route) => route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Visual audit fixture: data unavailable" }),
    }));

    for (const width of viewports) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      for (const route of routes) {
        await page.goto(route, { waitUntil: "domcontentloaded" });
        await page.waitForTimeout(35);
        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
        if (scrollWidth > width) overflow.push({ route, theme, width, scrollWidth });
      }
    }

    await context.close();
  }

  expect(overflow, JSON.stringify(overflow, null, 2)).toEqual([]);
});
