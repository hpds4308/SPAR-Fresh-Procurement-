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

export type ExcelOrderLinePreview = {
  row_number: number;
  product_code: string;
  description: string | null;
  unit_code: string | null;
  quantity: number | null;
  product_id: number | null;
  error: string | null;
};

export type ExcelOrderPreview = {
  lines: ExcelOrderLinePreview[];
  valid_line_count: number;
  error_count: number;
};

// Parses an uploaded order Excel (Product Code / POS Code / Product
// Description / Unit / Quantity columns) into a preview — never saves
// anything by itself. The caller reviews the result and still calls
// saveDraftOrder/submitOrder separately, the same as manual entry.
export function previewOrderExcel(file: File): Promise<ExcelOrderPreview> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch("/orders/draft/preview-excel", { method: "POST", body: formData });
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
