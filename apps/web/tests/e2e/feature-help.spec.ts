import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("feature help dialog", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
  });

  test("orders Platform between Build and Operate with Settings in System at the bottom", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".sidebar-nav")).toBeVisible();
    const labels = await page.locator(".sidebar-nav .nav-item span").allTextContents();
    expect(labels).toEqual([
      "Dashboard",
      "Agents",
      "Playground",
      "Workflows",
      "Tools",
      "Knowledge",
      "Memory",
      "MCP Servers",
      "Guardrails",
      "Deployments",
      "Approvals",
      "Traces",
      "Monitoring",
      "Evaluations",
      "Settings",
    ]);
    const systemGroup = page.locator(".nav-entry", { has: page.locator(".nav-group-label", { hasText: "System" }) });
    await expect(systemGroup.getByRole("link", { name: "Settings" })).toHaveAccessibleName("Settings");
  });

  test("opens from the feature title, contains focus, and closes with Escape", async ({ page }) => {
    const trigger = page.getByRole("button", { name: "How Sign in works" });
    await trigger.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Sign in" })).not.toBeFocused();
    const closeButton = dialog.getByRole("button", { name: "Close guide" });
    await expect(closeButton).toBeVisible();
    const colors = await closeButton.evaluate((button) => ({
      background: getComputedStyle(button).backgroundColor,
      primary: (() => {
        const probe = document.createElement("span");
        probe.style.backgroundColor = "var(--brand-primary)";
        button.append(probe);
        const color = getComputedStyle(probe).backgroundColor;
        probe.remove();
        return color;
      })(),
    }));
    expect(colors.background).toBe(colors.primary);
    await expect(dialog.getByRole("heading", { name: "What it is?" })).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "How it works" })).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Before you start" })).toHaveCount(0);

    for (let index = 0; index < 10; index += 1) await page.keyboard.press("Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);

    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
  });

  test("provides the guide content at a narrow viewport and has no serious dialog violations", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => localStorage.setItem("vf-theme", "light"));
    await page.reload();
    await page.getByRole("button", { name: "How Sign in works" }).click();

    const dialog = page.locator(".feature-help-dialog[open]");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "What it is?" })).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "How it works" })).toBeVisible();
    await expect(dialog.locator(".feature-help-body ul li")).toHaveCount(3);
    await expect(dialog.getByRole("heading", { name: "Related features" })).toHaveCount(0);

    const results = await new AxeBuilder({ page })
      .include(".feature-help-dialog[open]")
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious")).toEqual([]);
  });

  test("keeps the MCP eyebrow above its title and help button", async ({ page }) => {
    await page.goto("/mcp-servers");
    const eyebrow = page.locator(".mcp-page-header .panel-kicker");
    await expect(page.getByRole("heading", { name: "MCP Servers", exact: true })).toBeVisible();
    expect(await eyebrow.evaluate((element) => getComputedStyle(element).display)).toBe("block");
    const titleOffset = await page.locator(".mcp-page-header h1").evaluate((heading) => {
      const kicker = document.querySelector(".mcp-page-header .panel-kicker");
      return kicker ? heading.getBoundingClientRect().top - kicker.getBoundingClientRect().bottom : -1;
    });
    expect(titleOffset).toBeGreaterThanOrEqual(0);
    await expect(page.getByRole("button", { name: "How MCP servers works" })).toBeVisible();
  });
});
