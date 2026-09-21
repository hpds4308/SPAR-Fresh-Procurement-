import { test, expect } from "@playwright/test";
import { enterDashboard, loginAndEnter, loginUI, logoutUI, throttleLogin } from "./helpers";

/**
 * Critical flow 1 - authentication, role redirects, route guards, session refresh, logout.
 * Test IDs match qa/QA_REPORT.md section 4 (E2E-AUTH-xx).
 */
test.describe("E2E-AUTH", () => {
  test("AUTH-01 login page renders with labelled fields and a working show-password toggle", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByLabel("Username")).toBeVisible();
    await expect(page.getByLabel("Password")).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Show" }).click();
    await expect(page.getByLabel("Password")).toHaveAttribute("type", "text");
  });

  test("AUTH-02 wrong password shows a friendly error and stays on /login", async ({ page }) => {
    await loginUI(page, "br02", "not-the-password");
    await expect(page.getByText("Incorrect username or password.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  for (const [user, path, heading] of [
    ["admin", "/admin", /Procurement Dashboard/],
    ["br02", "/branch", /Branch Dashboard/],
    ["sup01", "/supplier", /Supplier Dashboard/],
  ] as const) {
    test(`AUTH-03 ${user} lands on ${path}`, async ({ page }) => {
      await loginUI(page, user);
      await expect(page).toHaveURL(new RegExp(`${path}$`), { timeout: 20_000 });
      await enterDashboard(page);
      await expect(page.locator("header")).toContainText(heading);
    });
  }

  test("AUTH-04 route guard: unauthenticated /admin redirects to /login; branch user cannot open /admin or /supplier", async ({ page }) => {
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/login$/);
    await loginAndEnter(page, "br02");
    await expect(page).toHaveURL(/\/branch$/);
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/branch$/);
    await page.goto("/supplier");
    await expect(page).toHaveURL(/\/branch$/);
  });

  test("AUTH-05 expired access token is silently refreshed and the page keeps working", async ({ page }) => {
    await loginAndEnter(page, "br02");
    await page.evaluate(() => localStorage.setItem("spar_access_token", "expired.or.garbage"));
    await page.reload();
    await enterDashboard(page);
    await expect(page.locator("header")).toContainText("Branch Dashboard");
    const fresh = await page.evaluate(() => localStorage.getItem("spar_access_token"));
    expect(fresh).not.toBe("expired.or.garbage");
  });

  test("AUTH-06 logout clears tokens and back-button does not reveal the dashboard", async ({ page }) => {
    await loginAndEnter(page, "br02");
    await logoutUI(page, "br02");
    await expect(page).toHaveURL(/\/login$/);
    expect(await page.evaluate(() => localStorage.getItem("spar_access_token"))).toBeNull();
    expect(await page.evaluate(() => localStorage.getItem("spar_refresh_token"))).toBeNull();
    await page.goBack();
    await expect(page).not.toHaveURL(/\/branch$/);
  });

  test("AUTH-07 opening a second tab reuses the session (shared localStorage)", async ({ context, page }) => {
    await loginUI(page, "br02");
    await expect(page).toHaveURL(/\/branch$/, { timeout: 20_000 });
    const second = await context.newPage();
    await second.goto("/");
    await expect(second).toHaveURL(/\/branch$/);
  });

  // Known defect BUG-02: usernames are case-sensitive and the input has no autocapitalize="none".
  test("AUTH-08 [BUG-02] username typed as 'Br02' (phone auto-capitalisation) still logs in", async ({ page }) => {
    test.fail(true, "BUG-02: case-sensitive username match (auth_service.py:33)");
    await loginUI(page, "Br02");
    await expect(page).toHaveURL(/\/branch$/, { timeout: 10_000 });
  });

  test("AUTH-09 username input hints for mobile keyboards are present", async ({ page }) => {
    test.fail(true, "BUG-02 (UI half): #username has no autocapitalize/autocomplete/autocorrect attributes (LoginPage.tsx:80)");
    await page.goto("/login");
    await expect(page.locator("#username")).toHaveAttribute("autocapitalize", "none");
  });

  test.afterAll(async () => {
    await throttleLogin(); // leave budget for the next spec file
  });
});
