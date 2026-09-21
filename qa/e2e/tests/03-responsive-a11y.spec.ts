import { test, expect, Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import { apiLogin, throttleLogin } from "./helpers";

/**
 * Phase 5 - responsive layout (320/375/768/1024/1440) and WCAG 2.1 A/AA scan (axe-core).
 * Results are also written to e2e/results/*.json so the numbers in QA_REPORT.md are reproducible.
 */
const WIDTHS: Array<[number, number]> = [[320, 568], [375, 667], [768, 1024], [1024, 768], [1440, 900]];
const OUT = "results";
fs.mkdirSync(OUT, { recursive: true });

async function overflowX(page: Page) {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

async function seedSession(page: Page, username: string) {
  const s = await apiLogin(username);
  await page.addInitScript(([a, r]) => {
    localStorage.setItem("spar_access_token", a);
    localStorage.setItem("spar_refresh_token", r);
    sessionStorage.removeItem("spar_welcome_pending");
  }, [s.access, s.refresh]);
}

test.describe("RESP - login page", () => {
  for (const [w, h] of WIDTHS) {
    test(`RESP-LOGIN ${w}x${h}: no horizontal scroll and the Sign in button is reachable`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: h });
      await page.goto("/login");
      await expect(page.getByLabel("Username")).toBeVisible();
      expect(await overflowX(page)).toBeLessThanOrEqual(1);
      const btn = page.getByRole("button", { name: "Sign in" });
      await btn.scrollIntoViewIfNeeded().catch(() => {});
      const box = await btn.boundingBox();
      const inView = !!box && box.y >= 0 && box.y + box.height <= h && box.x >= 0 && box.x + box.width <= w;
      test.info().annotations.push({ type: "measure", description: `submit box=${JSON.stringify(box)} inViewport=${inView}` });
      expect(inView, `Sign in button is outside the ${w}x${h} viewport and the page cannot scroll (h-screen overflow-hidden, LoginPage.tsx:39)`).toBeTruthy();
    });
  }

  test("RESP-LOGIN-LANDSCAPE 667x375 phone in landscape: Sign in reachable", async ({ page }) => {
    test.fail(true, "BUG-14: login card is h-screen overflow-hidden with a ~560px form; Sign in is clipped below 375px height and cannot be scrolled to (LoginPage.tsx:39)");
    await page.setViewportSize({ width: 667, height: 375 });
    await page.goto("/login");
    const box = await page.getByRole("button", { name: "Sign in" }).boundingBox();
    expect(box && box.y + box.height <= 375, `button bottom=${box && box.y + box.height}px in a 375px-high viewport`).toBeTruthy();
  });

  test("RESP-LOGIN-FORGOT 375x667 after opening 'Forgot password?' help the Sign in button is still reachable", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/login");
    await page.getByRole("button", { name: "Forgot password?" }).click();
    const box = await page.getByRole("button", { name: "Sign in" }).boundingBox();
    expect(box && box.y + box.height <= 667, `button bottom=${box && box.y + box.height}`).toBeTruthy();
  });
});

test.describe("RESP - dashboards", () => {
  for (const [w, h] of WIDTHS) {
    test(`RESP-BRANCH ${w}x${h}: no horizontal scroll, navigation reachable, order actions visible`, async ({ page }) => {
      await seedSession(page, "br05");
      await page.setViewportSize({ width: w, height: h });
      await page.goto("/branch");
      await expect(page.locator("header")).toBeVisible();
      expect(await overflowX(page)).toBeLessThanOrEqual(1);
      const nav = w < 768 ? page.getByRole("button", { name: /menu|open navigation/i }) : page.locator("aside");
      await expect(nav.first()).toBeVisible();
      await expect(page.getByRole("button", { name: "Save Order" })).toBeVisible();
    });
  }

  for (const [w, h] of WIDTHS.slice(0, 3)) {
    test(`RESP-ADMIN ${w}x${h}: order matrix table is usable (no page-level horizontal scroll)`, async ({ page }) => {
      await seedSession(page, "admin");
      await page.setViewportSize({ width: w, height: h });
      await page.goto("/admin");
      await expect(page.locator("header")).toBeVisible();
      const over = await overflowX(page);
      test.info().annotations.push({ type: "measure", description: `page overflow-x=${over}px` });
      expect(over).toBeLessThanOrEqual(1);
    });
  }
});

test.describe("A11Y - axe-core WCAG 2.1 A/AA", () => {
  const pages: Array<[string, string | null, string]> = [
    ["login", null, "/login"],
    ["branch-new-order", "br05", "/branch"],
    ["admin-dashboard", "admin", "/admin"],
    ["supplier-dashboard", "sup01", "/supplier"],
  ];
  for (const [name, user, path] of pages) {
    test(`A11Y-${name}: no critical/serious violations`, async ({ page }) => {
      test.fail(true, "BUG-16 (a11y): axe reports serious colour-contrast failures on every screen, plus select-name (critical) on admin/supplier dashboards - see results/axe-*.json");
      if (user) await seedSession(page, user);
      await page.setViewportSize({ width: 1024, height: 768 });
      await page.goto(path);
      if (user) await expect(page.locator("header")).toBeVisible();
      await page.waitForTimeout(800);
      const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      const summary = res.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length }));
      fs.writeFileSync(`${OUT}/axe-${name}.json`, JSON.stringify({ url: path, violations: summary, passes: res.passes.length }, null, 2));
      test.info().annotations.push({ type: "axe", description: JSON.stringify(summary) });
      const bad = res.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
      expect.soft(bad.map((v) => `${v.id} (${v.impact}) x${v.nodes.length}`), "critical/serious WCAG violations").toEqual([]);
    });
  }

  test("A11Y-keyboard: 'Show password' toggle can be reached with the Tab key", async ({ page }) => {
    test.fail(true, "A11Y: the Show/Hide button has tabIndex={-1} (LoginPage.tsx:105) so keyboard users cannot reveal the password");
    await page.goto("/login");
    await page.getByLabel("Password").focus();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: /Show|Hide/ })).toBeFocused();
  });

  test.afterAll(async () => {
    await throttleLogin();
  });
});
