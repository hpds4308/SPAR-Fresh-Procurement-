import { test, expect, request as pwRequest, APIRequestContext } from "@playwright/test";
import {
  Session, apiCall, apiLogin, deliveryDate, gotoTab, isSupplierSubmissionDay, loginAndEnter, logoutUI, openWindows, productRow,
} from "./helpers";

/**
 * Critical flows 2-5, one procurement cycle end to end, in order:
 *   2. Branch places an order (draft -> submit -> locked, visible in My Orders)
 *   3. Admin sees demand in the Order Matrix and downloads the Excel export
 *   4. Supplier submits prices (Mon/Wed/Fri only) and Admin sees them
 *   5. Admin assigns the supplier -> order flips to ASSIGNED -> supplier sees the confirmed order
 *      -> branch confirms delivery (with a shortage) -> CONFIRMED
 *
 * State is shared through the database, so the file runs serially. Reset with `python qa/reset_qa_db.py`
 * before a re-run on the same day (an order per branch per day can only be placed once - by design).
 */
test.describe.configure({ mode: "serial" });

const PRODUCT_CODE = "4503253"; // AVOCADO (seed data)
const PRODUCT_NAME = "AVOCADO";
const QTY = "12.5";
const PRICE = "450";

let ctx: APIRequestContext;
let admin: Session;

test.beforeAll(async () => {
  ctx = await pwRequest.newContext();
  admin = await apiLogin("admin");
  await openWindows(ctx, admin);
});
test.afterAll(async () => ctx.dispose());

test.describe("E2E-CYCLE", () => {
  test("ORDER-01 branch saves a draft, reloads and finds it, then submits; order form locks", async ({ page }) => {
    await loginAndEnter(page, "br02");
    const row = productRow(page, PRODUCT_CODE);
    await row.locator("input[type=number]").fill(QTY);
    await expect(page.getByText(/1 products? with a quantity entered/)).toBeVisible();

    await page.getByRole("button", { name: "Save Order" }).click();
    await expect(page.getByText(/draft/i).first()).toBeVisible();

    await page.reload();
    await expect(productRow(page, PRODUCT_CODE).locator("input[type=number]")).toHaveValue(QTY);

    await page.getByRole("button", { name: "Submit Order" }).click();
    const confirm = page.getByRole("dialog").getByRole("button", { name: /submit|confirm|yes/i });
    if (await confirm.isVisible().catch(() => false)) await confirm.click();

    await expect(page.getByText("Order submitted successfully.")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/now read-only/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Submit Order" })).toHaveCount(0);
  });

  test("ORDER-02 submitted order shows in My Orders as SUBMITTED for the right delivery date", async ({ page }) => {
    await loginAndEnter(page, "br02");
    await gotoTab(page, "My Orders");
    await expect(page.getByText(/SUBMITTED/i).first()).toBeVisible();
    const d = new Date(deliveryDate() + "T00:00:00");
    await expect(page.locator("main")).toContainText(String(d.getDate()));
  });

  test("ORDER-03 [API] a second submission for the same day is rejected", async () => {
    const branch = await apiLogin("br02");
    const r = await apiCall(ctx, branch, "post", "/orders", { lines: [{ product_id: 1, quantity: 1 }] });
    expect(r.status()).toBe(422);
    expect((await r.json()).detail).toMatch(/already been submitted/i);
  });

  test("ADMIN-01 order matrix shows Kandy's 12.5 kg AVOCADO for the delivery date; Excel export downloads", async ({ page }) => {
    await loginAndEnter(page, "admin");
    await gotoTab(page, "Branch Orders");
    await expect(page.locator("main")).toContainText("AVOCADO", { timeout: 20_000 });
    const matrixRow = page.locator("tr", { hasText: PRODUCT_NAME }).first();
    await expect(matrixRow).toContainText(QTY.replace(/\.0+$/, ""));

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: /Download Excel/i }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^order-matrix.*\.xlsx$/);
    // BUG-13: the API sends a dated filename but the SPA (different origin) cannot read Content-Disposition because
    // CORS does not expose it, so it always falls back to a generic name. Recorded in an annotation, asserted below.
    test.info().annotations.push({ type: "BUG-13", description: `downloaded as "${download.suggestedFilename()}" instead of a dated name` });
    const path = await download.path();
    const fs = await import("node:fs");
    const bytes = fs.readFileSync(path!);
    expect(bytes.length).toBeGreaterThan(2000);
    expect(bytes.subarray(0, 2).toString()).toBe("PK"); // a real .xlsx is a zip container
  });

  test("PRICE-01 supplier submits a price (Mon/Wed/Fri only) and Admin sees it in Supplier Prices", async ({ page }) => {
    test.skip(!isSupplierSubmissionDay(), "Supplier price window only opens Mon/Wed/Fri (Asia/Colombo)");
    await loginAndEnter(page, "sup01");
    await gotoTab(page, "Submit Prices");
    await productRow(page, PRODUCT_CODE).locator("input[type=number]").fill(PRICE);
    await page.getByRole("button", { name: /Submit/i }).last().click();
    const confirm = page.getByRole("dialog").getByRole("button", { name: /submit|confirm|yes/i });
    if (await confirm.isVisible().catch(() => false)) await confirm.click();
    await expect(page.getByText(/submitted|saved|success/i).first()).toBeVisible({ timeout: 15_000 });

    const sup = await apiLogin("sup01");
    const mine = await (await apiCall(ctx, sup, "get", `/pricing/mine?delivery_date=${deliveryDate()}`)).json();
    expect(mine.find((p: any) => p.product_code === PRODUCT_CODE)?.price).toBe(Number(PRICE));

    const all = await (await apiCall(ctx, admin, "get", `/pricing/admin?delivery_date=${deliveryDate()}`)).json();
    expect(all.some((p: any) => p.product_code === PRODUCT_CODE && p.price === Number(PRICE))).toBeTruthy();
  });

  test("ASSIGN-01 admin assigns the supplier -> order becomes ASSIGNED; supplier sees the confirmed order", async ({ page }) => {
    test.skip(!isSupplierSubmissionDay(), "Needs PRICE-01 data (supplier prices only exist on Mon/Wed/Fri)");
    const products = await (await apiCall(ctx, admin, "get", "/products")).json();
    const productId = products.find((p: any) => p.product_code === PRODUCT_CODE).id;
    const suppliers = await (await apiCall(ctx, admin, "get", "/suppliers")).json();
    const sup01 = suppliers.find((s: any) => /bloomax/i.test(s.supplier_name) || s.supplier_code === "SUP01");

    const put = await apiCall(ctx, admin, "put", `/orders/admin/product/${productId}/assignments?delivery_date=${deliveryDate()}`, {
      assignments: [{ supplier_id: sup01.id, quantity: Number(QTY), agreed_price: Number(PRICE) }],
    });
    expect(put.status()).toBe(200);
    expect((await put.json()).fully_assigned).toBe(true);

    await loginAndEnter(page, "br02");
    await gotoTab(page, "My Orders");
    await expect(page.getByText(/ASSIGNED/i).first()).toBeVisible();
  });

  test("SUPPLIER-01 [RISK-05] the assignment exists in the API but the supplier UI has no screen that shows it", async ({ page }) => {
    test.skip(!isSupplierSubmissionDay(), "Needs ASSIGN-01 data");
    const sup = await apiLogin("sup01");
    const mine = await (await apiCall(ctx, sup, "get", `/assignments/mine?delivery_date=${deliveryDate()}`)).json();
    expect(JSON.stringify(mine)).toContain(PRODUCT_NAME); // data is there (GET /assignments/mine works)

    await loginAndEnter(page, "sup01");
    const tabs = await page.locator("aside nav button").allInnerTexts();
    // README (Phase 5d) promises a "Confirmed Orders" tab; frontend/src/api/assignments.ts fetchMyAssignments() is never called.
    test.info().annotations.push({ type: "RISK-05", description: `Supplier tabs are: ${tabs.map((t) => t.trim()).join(" | ")}` });
    expect(tabs.join(" ")).not.toMatch(/Confirmed Orders/);
    await gotoTab(page, "Orders by Branch");
    await expect(page.locator("main")).not.toContainText(PRODUCT_NAME); // Order-Matrix assignments do not appear here
  });

  test("CONFIRM-01 branch confirms delivery with a shortage -> order becomes CONFIRMED and the shortage is highlighted", async ({ page }) => {
    test.skip(!isSupplierSubmissionDay(), "Needs ASSIGN-01 data");
    await loginAndEnter(page, "br02");
    await gotoTab(page, "My Orders");
    await page.getByText(/ASSIGNED/i).first().click();
    await page.getByRole("button", { name: "Confirm Delivery" }).first().click();
    await page.locator("main input[type=number]").first().fill("10");
    await page.getByRole("button", { name: /Confirm Delivery|Confirming/ }).last().click();
    await expect(page.getByText(/CONFIRMED/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("main")).toContainText(/12\.5/);
    await expect(page.locator("main")).toContainText(/12[.]5.*10/);
  });
});

test.describe("E2E-EXPORT", () => {
  test("EXPORT-02 [BUG-13] downloaded export keeps the server's dated filename (needs Access-Control-Expose-Headers)", async ({ page }) => {
    test.fail(true, "BUG-13: main.py CORSMiddleware has no expose_headers=['Content-Disposition']; api/orders.ts:180-186 falls back to 'order-matrix.xlsx'");
    await loginAndEnter(page, "admin");
    await gotoTab(page, "Branch Orders");
    await expect(page.locator("main")).toContainText("AVOCADO", { timeout: 20_000 });
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Download Excel/i }).click()]);
    expect(download.suggestedFilename()).toMatch(/^order-matrix-\d{4}-\d{2}-\d{2}\.xlsx$/);
  });
});
