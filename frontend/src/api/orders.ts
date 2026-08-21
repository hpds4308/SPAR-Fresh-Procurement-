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

export function confirmDelivery(
  orderId: number,
  lines: { product_id: number; received_quantity: number; notes?: string }[]
): Promise<Order> {
  return apiFetch(`/orders/${orderId}/confirm-delivery`, {
    method: "PUT",
    body: JSON.stringify({ lines }),
  });
}

export function cancelOrder(orderId: number): Promise<{ detail: string }> {
  return apiFetch(`/orders/${orderId}/cancel`, { method: "POST" });
}
