import { test, expect, request as pwRequest } from "@playwright/test";
import { API, PASSWORD } from "./helpers";

/** Runs last: it deliberately exhausts the login rate limit (10/min/IP), then waits for the window to clear. */
test.describe("E2E-RATELIMIT", () => {
  test("RATE-01 [BUG-15] a rate-limited login attempt shows an understandable message, not 'Request failed with status 429.'", async ({ page }) => {
    test.fail(true, "BUG-15: slowapi's 429 body is {error: ...} but api/client.ts:77-78 only reads {detail}");
    const ctx = await pwRequest.newContext();
    for (let i = 0; i < 11; i++) await ctx.post(`${API}/auth/login`, { data: { username: "nobody", password: "x" } });
    const raw = await ctx.post(`${API}/auth/login`, { data: { username: "nobody", password: "x" } });
    expect(raw.status()).toBe(429);
    expect(Object.keys(await raw.json())).toEqual(["error"]); // no 'detail' key
    await ctx.dispose();

    await page.goto("/login");
    await page.getByLabel("Username").fill("br02");
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText(/too many|try again|wait/i)).toBeVisible({ timeout: 5000 });
  });

  test.afterAll(async () => {
    await new Promise((r) => setTimeout(r, 62_000)); // let the limiter window clear for whoever runs next
  });
});
