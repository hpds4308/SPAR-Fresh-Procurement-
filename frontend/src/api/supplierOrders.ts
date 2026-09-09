import { apiFetch } from "./client";

export type SupplierOrderItem = {
  id: number;
  branch_id: number;
  branch_name: string;
  product_id: number;
  product_code: string;
  product_description: string;
  category_name: string;
  quantity: number;
  unit_code: string;
  agreed_price: number | null;
  effective_price: number | null;
  price_is_estimated: boolean;
  price_as_of: string | null;
  notes: string | null;
  line_total: number | null;
};

export type SupplierOrderAdmin = {
  supplier_id: number;
  supplier_name: string;
  delivery_date: string;
  items: SupplierOrderItem[];
};

export type BranchOrderGroup = {
  branch_id: number;
  branch_name: string;
  items: SupplierOrderItem[];
  branch_total: number;
};

export type MySupplierOrders = {
  delivery_date: string | null;
  branches: BranchOrderGroup[];
  grand_total: number;
  available_delivery_dates: string[];
};

export type SupplierOrderItemInput = {
  branch_id: number;
  product_id: number;
  quantity: number;
  agreed_price?: number | null;
  notes?: string | null;
};

export function fetchMySupplierOrders(deliveryDate?: string): Promise<MySupplierOrders> {
  const qs = deliveryDate ? `?delivery_date=${deliveryDate}` : "";
  return apiFetch(`/supplier-orders/mine${qs}`);
}

export async function downloadMySupplierOrders(deliveryDate?: string): Promise<void> {
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const qs = deliveryDate ? `?delivery_date=${deliveryDate}` : "";
  const access = localStorage.getItem("spar_access_token");
  const res = await fetch(`${API_BASE}/api/v1/supplier-orders/mine/export${qs}`, {
    headers: access ? { Authorization: `Bearer ${access}` } : {},
  });
  if (!res.ok) {
    throw new Error("Could not download your orders.");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "orders-by-branch.xlsx";

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export function fetchSupplierOrderAdmin(supplierId: number, deliveryDate: string): Promise<SupplierOrderAdmin> {
  return apiFetch(`/supplier-orders/admin?supplier_id=${supplierId}&delivery_date=${deliveryDate}`);
}

export type SupplierOrderSummary = {
  supplier_id: number;
  supplier_name: string;
  delivery_date: string;
  line_count: number;
  total_value: number;
};

// Powers the Supplier-wise side of Admin Order History — mirrors
// fetchOrderDates/fetchOrdersForDate on the Branch-wise side.
export function fetchSupplierOrderDates(): Promise<string[]> {
  return apiFetch("/supplier-orders/admin/dates");
}

export function fetchSupplierOrderSummaries(deliveryDate: string): Promise<SupplierOrderSummary[]> {
  return apiFetch(`/supplier-orders/admin/summary?delivery_date=${deliveryDate}`);
}

export function setSupplierOrderAdmin(
  supplierId: number,
  deliveryDate: string,
  items: SupplierOrderItemInput[]
): Promise<SupplierOrderAdmin> {
  return apiFetch(`/supplier-orders/admin?supplier_id=${supplierId}&delivery_date=${deliveryDate}`, {
    method: "PUT",
    body: JSON.stringify({ items }),
  });
}

// Total quantity per product already given to OTHER suppliers for this
// delivery date — pass the supplier currently being edited as
// excludeSupplierId so their own saved lines don't count against
// themselves while deciding how much more (if any) to give them.
export function fetchAssignedQuantities(
  deliveryDate: string,
  excludeSupplierId?: number
): Promise<Record<number, number>> {
  const qs = new URLSearchParams({ delivery_date: deliveryDate });
  if (excludeSupplierId !== undefined) qs.set("exclude_supplier_id", String(excludeSupplierId));
  return apiFetch(`/supplier-orders/admin/assigned?${qs.toString()}`);
}

// Same as fetchAssignedQuantities, broken down per branch — key is
// "product_id:branch_id", matching the grid's own cellKey convention.
// Powers each branch column's remaining-quantity placeholder.
export function fetchAssignedQuantitiesByBranch(
  deliveryDate: string,
  excludeSupplierId?: number
): Promise<Record<string, number>> {
  const qs = new URLSearchParams({ delivery_date: deliveryDate });
  if (excludeSupplierId !== undefined) qs.set("exclude_supplier_id", String(excludeSupplierId));
  return apiFetch(`/supplier-orders/admin/assigned-by-branch?${qs.toString()}`);
}

export type SupplierAssignedProduct = {
  product_id: number;
  quantity: number;
  agreed_price: number;
};

// Products already assigned to this supplier for this delivery date via
// Product Assignment (Order Matrix) — powers "Fill from assignments" on
// the Order Builder grid.
export function fetchAssignmentsForSupplier(
  supplierId: number,
  deliveryDate: string
): Promise<SupplierAssignedProduct[]> {
  const qs = new URLSearchParams({ supplier_id: String(supplierId), delivery_date: deliveryDate });
  return apiFetch(`/supplier-orders/admin/assignments?${qs.toString()}`);
}

export type SupplierPricePreview = {
  product_id: number;
  price: number;
  is_estimated: boolean;
  as_of: string;
};

// This supplier's resolved price per product — same price-resolution
// rule used everywhere else (sent adjusted price > submitted price >
// most recent known price, flagged as an estimate). Shown as a
// reference column on the Order Builder before any line is saved.
export function fetchSupplierPricePreview(
  supplierId: number,
  deliveryDate: string
): Promise<SupplierPricePreview[]> {
  const qs = new URLSearchParams({ supplier_id: String(supplierId), delivery_date: deliveryDate });
  return apiFetch(`/supplier-orders/admin/prices?${qs.toString()}`);
}
