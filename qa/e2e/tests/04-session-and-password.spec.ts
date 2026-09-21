import { test, expect, request as pwRequest, APIRequestContext } from "@playwright/test";
import { API, Session, apiCall, apiLogin, enterDashboard, loginUI, logoutUI, throttleLogin } from "./helpers";

/**
 * Fixes for SEC-01 (forced password change) and BUG-03 (revocable sessions), end to end in the browser.
 * Uses br09 / sup09-style accounts nobody else touches. `python qa/reset_qa_db.py` restores the seeded
 * password so the file can be re-run.
 */
test.describe.configure({ mode: "serial" });

const USER = "br09";
const NEW_PASSWORD = "Galle-Fresh-2026!";

let ctx: APIRequestContext;
let admin: Session;
let tempPassword: string;

test.beforeAll(async () => {
  ctx = await pwRequest.newContext();
  admin = await apiLogin("admin");
  const users = await (await apiCall(ctx, admin, "get", "/users")).json();
  const target = users.find((u: any) => u.username === USER);
  const reset = await apiCall(ctx, admin, "post", `/users/${target.id}/reset-password`);
  expect(reset.status()).toBe(200);
  tempPassword = (await reset.json()).temporary_password; // an admin-issued temporary password => must be changed
});
test.afterAll(async () => ctx.dispose());

test.describe("E2E-PASSWORD", () => {
  test("PW-01 first sign-in with a temporary/seeded password lands on the change-password screen, not the dashboard", async ({ page }) => {
    await loginUI(page, USER, tempPassword);
    await expect(page.getByRole("heading", { name: "Choose your own password" })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("header")).toHaveCount(0); // no dashboard shell rendered behind it
  });

  test("PW-02 the screen cannot be bypassed by typing a dashboard URL", async ({ page }) => {
    await loginUI(page, USER, tempPassword);
    await expect(page.getByRole("heading", { name: "Choose your own password" })).toBeVisible({ timeout: 20_000 });
    for (const path of ["/branch", "/", "/admin", "/supplier"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: "Choose your own password" })).toBeVisible();
    }
  });

  test("PW-03 the API refuses everything except the way out while the change is pending", async () => {
    const tokens = await (await (await pwRequest.newContext()).post(`${API}/auth/login`, { data: { username: USER, password: tempPassword } })).json();
    const session: Session = { access: tokens.access_token, refresh: tokens.refresh_token };
    expect(tokens.must_change_password).toBe(true);
    expect((await apiCall(ctx, session, "get", "/orders/window")).status()).toBe(403);
    expect((await apiCall(ctx, session, "get", "/products")).status()).toBe(403);
    expect((await apiCall(ctx, session, "get", "/auth/me")).status()).toBe(200);
  });

  test("PW-04 validation: unchanged, too short and mismatched passwords are rejected with a clear message", async ({ page }) => {
    await loginUI(page, USER, tempPassword);
    await expect(page.getByRole("heading", { name: "Choose your own password" })).toBeVisible({ timeout: 20_000 });
    const fill = async (cur: string, next: string, confirm: string) => {
      await page.getByLabel("Current password").fill(cur);
      await page.getByLabel("New password", { exact: true }).fill(next);
      await page.getByLabel("Confirm new password").fill(confirm);
      await page.getByRole("button", { name: "Save new password" }).click();
    };
    await fill(tempPassword, tempPassword, tempPassword);
    await expect(page.getByRole("alert")).toContainText("different from the current");
    await fill(tempPassword, "short", "short");
    await expect(page.getByLabel("New password", { exact: true })).toHaveJSProperty("validity.valid", false); // native minlength
    await fill(tempPassword, NEW_PASSWORD, NEW_PASSWORD + "x");
    await expect(page.getByRole("alert")).toContainText("don't match");
    await fill(tempPassword, "ChangeMe123!", "ChangeMe123!");
    await expect(page.getByRole("alert")).toContainText(/too easy to guess|different/);
  });

  test("PW-05 choosing a new password signs the user straight in (fresh tokens) and the dashboard appears", async ({ page }) => {
    await loginUI(page, USER, tempPassword);
    await expect(page.getByRole("heading", { name: "Choose your own password" })).toBeVisible({ timeout: 20_000 });
    await page.getByLabel("Current password").fill(tempPassword);
    await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
    await page.getByLabel("Confirm new password").fill(NEW_PASSWORD);
    await page.getByRole("button", { name: "Save new password" }).click();
    await enterDashboard(page);
    await expect(page.locator("header")).toContainText("Branch Dashboard");
    await expect(page).toHaveURL(/\/branch$/);
  });

  test("PW-06 the temporary password stopped working; the new one works and no longer forces a change", async ({ page }) => {
    const c = await pwRequest.newContext();
    await throttleLogin();
    expect((await c.post(`${API}/auth/login`, { data: { username: USER, password: tempPassword } })).status()).toBe(401);
    await c.dispose();
    await loginUI(page, USER, NEW_PASSWORD);
    await enterDashboard(page);
    await expect(page.getByRole("heading", { name: "Choose your own password" })).toHaveCount(0);
  });

  test("PW-07 logging out revokes that session's refresh token on the server", async ({ page }) => {
    await loginUI(page, USER, NEW_PASSWORD);
    await enterDashboard(page);
    const refresh = await page.evaluate(() => localStorage.getItem("spar_refresh_token"));
    expect(refresh).toBeTruthy();
    await logoutUI(page, USER);
    await expect(page).toHaveURL(/\/login$/);
    const r = await ctx.post(`${API}/auth/refresh`, { data: { refresh_token: refresh } });
    expect(r.status()).toBe(401); // before the fix this returned 200 and stayed valid for 7 days
  });

  test("PW-08 signing out on one device leaves another device on the same shared login signed in", async ({ browser }) => {
    const a = await browser.newContext();
    const b = await browser.newContext();
    const pageA = await a.newPage();
    const pageB = await b.newPage();
    await loginUI(pageA, USER, NEW_PASSWORD);
    await enterDashboard(pageA);
    await loginUI(pageB, USER, NEW_PASSWORD);
    await enterDashboard(pageB);
    await logoutUI(pageA, USER);
    await expect(pageA).toHaveURL(/\/login$/);
    await pageB.reload();
    await enterDashboard(pageB);
    await expect(pageB.locator("header")).toContainText("Branch Dashboard");
    await a.close();
    await b.close();
  });
});
