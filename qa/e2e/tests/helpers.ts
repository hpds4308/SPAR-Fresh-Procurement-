import { APIRequestContext, Page, expect, request as pwRequest } from "@playwright/test";

export const API = process.env.QA_API_URL ?? "http://127.0.0.1:8000/api/v1";
export const PASSWORD = process.env.QA_PASSWORD ?? "ChangeMe123!";

export type Session = { access: string; refresh: string };

// The API rate-limits POST /auth/login to 10/minute per client IP. Every login in this suite (API or UI)
// goes through here so the suite paces itself instead of tripping the limit and failing for the wrong reason.
const loginStamps: number[] = [];
export async function throttleLogin() {
  const now = Date.now();
  while (loginStamps.length && now - loginStamps[0] > 61_000) loginStamps.shift();
  if (loginStamps.length >= 6) {
    await new Promise((r) => setTimeout(r, 61_000 - (now - loginStamps[0])));
  }
  loginStamps.push(Date.now());
}

/** Log in through the API (fast path for test setup - the UI login is tested separately). */
export async function apiLogin(username: string, password = PASSWORD): Promise<Session> {
  await throttleLogin();
  const ctx = await pwRequest.newContext();
  const res = await ctx.post(`${API}/auth/login`, { data: { username, password } });
  if (res.status() === 429) throw new Error("Login rate limit hit (10/min per IP) - wait a minute and re-run");
  expect(res.status(), `API login for ${username}`).toBe(200);
  const body = await res.json();
  await ctx.dispose();
  return { access: body.access_token, refresh: body.refresh_token };
}

export async function apiCall(
  ctx: APIRequestContext,
  s: Session,
  method: "get" | "post" | "put" | "patch" | "delete",
  path: string,
  data?: unknown,
) {
  return ctx[method](`${API}${path}`, { headers: { Authorization: `Bearer ${s.access}` }, data });
}

/** Keep the branch/supplier cut-offs open regardless of the clock, so tests are deterministic. */
export async function openWindows(ctx: APIRequestContext, admin: Session) {
  for (const key of ["branch_order_deadline", "supplier_price_deadline"]) {
    const r = await apiCall(ctx, admin, "put", `/settings/${key}`, { value: "23:59" });
    expect(r.status(), `set ${key}`).toBe(200);
  }
}

export async function loginUI(page: Page, username: string, password = PASSWORD) {
  await throttleLogin();
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

export async function gotoTab(page: Page, name: string | RegExp) {
  await page.locator("aside").getByText(name, { exact: typeof name === "string" }).first().click();
}

/** Delivery date the app will use for an order placed today (order date + 2, business TZ Asia/Colombo). */
export function deliveryDate(): string {
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Colombo" }));
  now.setDate(now.getDate() + 2);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}

export function colomboWeekday(): number {
  return new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Colombo" })).getDay(); // 0=Sun
}

/** Supplier price submission is only allowed Mon/Wed/Fri (pricing_service.SUBMISSION_WEEKDAYS). */
export function isSupplierSubmissionDay(): boolean {
  return [1, 3, 5].includes(colomboWeekday());
}

export function productRow(page: Page, productCode: string) {
  return page.locator("div.divide-y > div").filter({ has: page.getByText(productCode, { exact: true }) });
}

/** Branch and Supplier logins land on a welcome splash first (video, auto-continues after ~20s). Click through it. */
export async function enterDashboard(page: Page) {
  const cont = page.getByRole("button", { name: /Continue to Dashboard/i });
  const header = page.locator("header");
  await expect(cont.or(header)).toBeVisible({ timeout: 30_000 });
  if (await cont.isVisible().catch(() => false)) await cont.click();
  await expect(header).toBeVisible();
}

export async function loginAndEnter(page: Page, username: string, password = PASSWORD) {
  await loginUI(page, username, password);
  await enterDashboard(page);
}

export async function logoutUI(page: Page, username: string) {
  await page.locator("header").getByRole("button", { name: new RegExp(username, "i") }).click();
  await page.getByRole("button", { name: "Logout" }).click();
  await page.getByRole("button", { name: "Log out" }).click();
}
