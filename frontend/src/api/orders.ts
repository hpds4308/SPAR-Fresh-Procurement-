import { apiFetch } from "./client";

export type Product = {
  id: number;
  product_code: string;
  description: string;
  category_name: string;
  subcategory: string | null;
  unit_code: string;
  status: string;
};

// Fixed display grouping for every product listing across the app:
// Fruit, then Vege Low, then Vege Pola, then Vege Up — alphabetical by
// item name within each category. An unrecognized category name (should
// never happen with today's 4 categories) sorts last rather than first,
// so it stays visible instead of silently jumping to the top.
const CATEGORY_DISPLAY_ORDER = ["Fruit", "Vege Low", "Vege Pola", "Vege Up"];

function categoryRank(categoryName: string): number {
  const idx = CATEGORY_DISPLAY_ORDER.indexOf(categoryName);
  return idx === -1 ? CATEGORY_DISPLAY_ORDER.length : idx;
}

export function compareProductDisplayOrder(
  a: { category_name: string; description: string },
  b: { category_name: string; description: string }
): number {
  return categoryRank(a.category_name) - categoryRank(b.category_name) || a.description.localeCompare(b.description);
}

export type OrderWindow = {
  is_open: boolean;
  delivery_date: string; // YYYY-MM-DD
  cutoff_time: string; // HH:MM
  server_time: string; // ISO
};

export type OrderLine = {
  id: number;
  product_id: number;
  product_code: string;
  product_description: string;
  quantity: number;
  unit_code: string;
  notes: string | null;
  received_quantity: number | null;
  receipt_notes: string | null;
  added_by_admin: boolean;
};

export type Order = {
  id: number;
  branch_id: number;
  branch_name: string;
  order_date: string;
  delivery_date: string;
  status: string;
  notes: string | null;
  submitted_by_username: string;
  confirmed_at: string | null;
  confirmed_by_username: string | null;
  // Set when the branch submitted nothing by the cutoff and the system
  // submitted this order for them: "LAST_WEEK" = copied from the branch's
  // own order on the same weekday, auto_weeks_back weeks earlier (1 = the
  // previous week); "DRAFT" = the branch's unsent draft. "LATEST" only
  // appears on orders from the earlier any-weekday fallback.
  auto_submitted: boolean;
  auto_submit_source: "LAST_WEEK" | "LATEST" | "DRAFT" | null;
  auto_source_order_date: string | null;
  auto_weeks_back: number | null;
  auto_reviewed: boolean;
  lines: OrderLine[];
};

export type OrderSummary = {
  id: number;
  branch_id: number;
  branch_name: string;
  order_date: string;
  delivery_date: string;
  status: string;
  line_count: number;
  has_admin_added_lines: boolean;
  auto_submitted: boolean;
  auto_submit_source: "LAST_WEEK" | "LATEST" | "DRAFT" | null;
  auto_source_order_date: string | null;
  auto_weeks_back: number | null;
  auto_reviewed: boolean;
};

export function fetchProducts(): Promise<Product[]> {
  return apiFetch("/products");
}

export function fetchOrderWindow(): Promise<OrderWindow> {
  return apiFetch("/orders/window");
}

export function fetchMyOrders(): Promise<OrderSummary[]> {
  return apiFetch("/orders");
}

export function fetchOrdersForDate(deliveryDate: string): Promise<OrderSummary[]> {
  return apiFetch(`/orders?delivery_date=${deliveryDate}`);
}

export function fetchOrderDates(): Promise<string[]> {
  return apiFetch("/orders/admin/dates");
}

export function fetchOrder(id: number): Promise<Order> {
  return apiFetch(`/orders/${id}`);
}

export function fetchMyOrderToday(): Promise<Order | null> {
  return apiFetch("/orders/mine/today");
}

// {product_id: current stock in hand}, from the POS system, for the
// branch's own location. A product with no entry means unknown, not
// zero — it's either not POS-tracked or the POS lookup couldn't run
// (not configured, or this branch has no location code set yet).
export function fetchStockInHand(): Promise<Record<number, number>> {
  return apiFetch("/orders/stock-in-hand");
}

export type MatrixBranchColumn = {
  branch_id: number;
  branch_code: string;
  branch_name: string;
  auto_submitted: boolean;
  auto_submit_source: "LAST_WEEK" | "LATEST" | "DRAFT" | null;
  auto_source_order_date: string | null;
  auto_weeks_back: number | null;
  auto_reviewed: boolean;
  // Missed the cutoff with nothing to auto-submit — no order for this date.
  no_order: boolean;
};

export type MatrixRow = {
  product_id: number;
  product_code: string;
  category_name: string;
  description: string;
  unit_code: string;
  quantities: Record<string, number>;
};

export type OrderMatrix = {
  delivery_date: string;
  branches: MatrixBranchColumn[];
  rows: MatrixRow[];
  available_delivery_dates: string[];
};

export function fetchOrderMatrix(deliveryDate?: string): Promise<OrderMatrix> {
  const qs = deliveryDate ? `?delivery_date=${deliveryDate}` : "";
  return apiFetch(`/orders/admin/matrix${qs}`);
}

type AutoSource = {
  auto_submit_source: "LAST_WEEK" | "LATEST" | "DRAFT" | null;
  auto_source_order_date: string | null;
  auto_weeks_back: number | null;
};

function shortDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

// "1 week back" / "3 weeks back" — which week the weekly fallback used.
export function weeksBackLabel(weeks: number | null): string | null {
  if (!weeks) return null;
  return weeks === 1 ? "previous week" : `${weeks} weeks back`;
}

// Short label that marks an order as system-submitted, never by the branch.
export function autoSubmitLabel(o: AutoSource): string {
  if (o.auto_submit_source === "DRAFT") return "Auto-Submitted — Unsent Draft";
  if (o.auto_submit_source === "LATEST") return "Auto-Submitted — Latest Previous Order";
  return "Auto-Submitted — Previous Week's Order";
}

// One-line explanation of where an auto-submitted order came from.
export function autoSubmitDescription(o: AutoSource): string {
  if (o.auto_submit_source === "DRAFT") return "Not submitted by the cutoff — the unsent draft was submitted automatically.";
  const from = o.auto_source_order_date ? shortDate(o.auto_source_order_date) : "an earlier date";
  if (o.auto_submit_source === "LATEST") {
    return `Not submitted by the cutoff — copied automatically from the latest previous order (placed ${from}).`;
  }
  const week = weeksBackLabel(o.auto_weeks_back);
  return `Not submitted by the cutoff — copied automatically from the same-weekday order placed ${from}${
    week ? ` (${week})` : ""
  }.`;
}

export type AutoSubmittedOrder = {
  order_id: number;
  branch_id: number;
  branch_name: string;
  order_date: string;
  delivery_date: string;
  auto_submit_source: "LAST_WEEK" | "LATEST" | "DRAFT";
  auto_source_order_date: string | null;
  auto_weeks_back: number | null;
  line_count: number;
};

// "No Previous Order Found": a branch that missed the cutoff with nothing to
// auto-submit (no draft, and no order on the same weekday within the
// lookback window), and still has no order for that date.
export type MissedOrderNotice = {
  notice_id: number;
  branch_id: number;
  branch_name: string;
  order_date: string;
  delivery_date: string;
};

export type AutoSubmitAttention = {
  orders: AutoSubmittedOrder[];
  missed: MissedOrderNotice[];
  lookback_weeks: number;
};

// Everything from the auto-submit job Admin hasn't dealt with yet: orders
// to review, and branches left with no order — drives the Branch Orders
// badge/banner.
export function fetchUnreviewedAutoOrders(): Promise<AutoSubmitAttention> {
  return apiFetch("/orders/admin/auto-submitted");
}

// Acknowledge one order, dismiss one notice, everything for a delivery date, or (no args) everything.
export function reviewAutoOrders(
  payload: { order_id?: number; notice_id?: number; delivery_date?: string } = {}
): Promise<{ reviewed: number }> {
  return apiFetch("/orders/admin/auto-submitted/review", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// Admin adds (or updates) one product/quantity directly on a branch's
// order for a delivery date — e.g. topping up what the branch itself
// ordered. Creates the branch's order for that date if it doesn't exist
// yet. Shows up highlighted on the branch's own "My Orders" as admin-added.
export function adminAddOrderLine(payload: {
  branch_id: number;
  product_id: number;
  delivery_date: string;
  quantity: number;
}): Promise<Order> {
  return apiFetch("/orders/admin/lines", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// Undoes a previous adminAddOrderLine call — e.g. it was added under the
// wrong delivery date by mistake. Only works on a line Admin added; the
// backend rejects it for a branch's own line. Returns null if removing it
// also removed the (now-empty) order.
export function adminRemoveOrderLine(payload: {
  branch_id: number;
  product_id: number;
  delivery_date: string;
}): Promise<Order | null> {
  return apiFetch("/orders/admin/lines/remove", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function orderMatrixExportUrl(deliveryDate?: string): string {
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const qs = deliveryDate ? `?delivery_date=${deliveryDate}` : "";
  return `${API_BASE}/api/v1/orders/admin/matrix/export${qs}`;
}

export async function downloadOrderMatrix(deliveryDate?: string): Promise<void> {
  const access = localStorage.getItem("spar_access_token");
  const res = await fetch(orderMatrixExportUrl(deliveryDate), {
    headers: access ? { Authorization: `Bearer ${access}` } : {},
  });
  if (!res.ok) {
    throw new Error("Could not download the order matrix.");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "order-matrix.xlsx";

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export function submitOrder(lines: { product_id: number; quantity: number; notes?: string }[], notes?: string): Promise<Order> {
  return apiFetch("/orders", {
    method: "POST",
    body: JSON.stringify({ lines, notes: notes || null }),
  });
}

export function saveDraftOrder(lines: { product_id: number; quantity: number; notes?: string }[], notes?: string): Promise<Order> {
  return apiFetch("/orders/draft", {
    method: "POST",
    body: JSON.stringify({ lines, notes: notes || null }),
  });
}

export function confirmDelivery(
  orderId: number,
  lines: { product_id: number; received_quantity: number; notes?: string }[]
): Promise<Order> {
  return apiFetch(`/orders/${orderId}/confirm-delivery`, {
    method: "PUT",
    body: JSON.stringify({ lines }),
  });
}
