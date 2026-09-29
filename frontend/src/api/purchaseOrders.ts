import { apiFetch } from "./client";

export type PurchaseOrderStatus = "ISSUED" | "CANCELLED";

export type PurchaseOrderLine = {
  product_id: number;
  product_code: string;
  product_description: string;
  unit_code: string;
  quantity: number;
  unit_price: number;
  line_total: number;
  price_is_estimated: boolean;
  notes: string | null;
};

export type BranchPurchaseOrder = {
  branch_id: number;
  branch_code: string;
  branch_name: string;
  branch_location: string | null;
  po_number: string;
  lines: PurchaseOrderLine[];
  total: number;
};

export type PurchaseOrderSummary = {
  id: number;
  po_number: string;
  revision: number;
  status: PurchaseOrderStatus;
  supplier_id: number;
  supplier_name: string;
  delivery_date: string;
  branch_count: number;
  line_count: number;
  total_amount: number;
  issued_at: string;
  issued_by_name: string | null;
  cancelled_at: string | null;
};

export type PurchaseOrder = PurchaseOrderSummary & {
  supplier: {
    supplier_id: number;
    supplier_code: string;
    supplier_name: string;
    contact_person: string | null;
    phone: string | null;
    email: string | null;
    address: string | null;
    company_number: string | null;
  };
  consolidated_lines: PurchaseOrderLine[];
  branches: BranchPurchaseOrder[];
  is_outdated: boolean;
};

export type PurchaseOrderAdminRow = {
  supplier_id: number;
  supplier_name: string;
  delivery_date: string;
  line_count: number;
  order_total: number;
  unpriced_line_count: number;
  purchase_order: PurchaseOrderSummary | null;
  is_outdated: boolean;
};

export function fetchPurchaseOrderDates(): Promise<string[]> {
  return apiFetch("/purchase-orders/admin/dates");
}

export function fetchAdminPurchaseOrders(deliveryDate: string): Promise<PurchaseOrderAdminRow[]> {
  return apiFetch(`/purchase-orders/admin?delivery_date=${deliveryDate}`);
}

export function fetchAdminPurchaseOrder(id: number): Promise<PurchaseOrder> {
  return apiFetch(`/purchase-orders/admin/${id}`);
}

export function issuePurchaseOrder(supplierId: number, deliveryDate: string): Promise<PurchaseOrder> {
  return apiFetch("/purchase-orders/admin", {
    method: "POST",
    body: JSON.stringify({ supplier_id: supplierId, delivery_date: deliveryDate }),
  });
}

export function cancelPurchaseOrder(id: number): Promise<PurchaseOrder> {
  return apiFetch(`/purchase-orders/admin/${id}/cancel`, { method: "POST" });
}

export function fetchMyPurchaseOrders(): Promise<PurchaseOrderSummary[]> {
  return apiFetch("/purchase-orders/mine");
}

export function fetchMyPurchaseOrder(id: number): Promise<PurchaseOrder> {
  return apiFetch(`/purchase-orders/mine/${id}`);
}

/** A branch's own branch POs — each cut down to just that branch's lines. */
export function fetchBranchPurchaseOrders(): Promise<PurchaseOrderSummary[]> {
  return apiFetch("/purchase-orders/branch");
}

export function fetchBranchPurchaseOrder(id: number): Promise<PurchaseOrder> {
  return apiFetch(`/purchase-orders/branch/${id}`);
}
