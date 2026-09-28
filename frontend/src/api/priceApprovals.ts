import { apiFetch } from "./client";

// Stored statuses, plus EXPIRED — a PENDING sheet whose delivery date has
// arrived. See backend price_approval_service.py.
export type SheetStatus = "PENDING" | "APPROVED" | "REJECTED" | "VOIDED" | "WITHDRAWN" | "EXPIRED";

// Row-level status on the price tables: no adjustment (null), DRAFT (not
// sent), or the status of the sheet it was sent on.
export type RowApprovalStatus = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | null;

export type PriceSheetItem = {
  supplier_price_id: number;
  product_id: number;
  product_code: string;
  product_description: string;
  unit_code: string;
  supplier_price: number;
  adjusted_price: number;
};

export type PriceSheetSummary = {
  id: number;
  supplier_id: number;
  supplier_name: string;
  delivery_date: string;
  status: SheetStatus;
  item_count: number;
  sent_at: string;
  sent_by_name: string | null;
  responded_at: string | null;
  responded_by_name: string | null;
  signer_name: string | null;
  rejection_reason: string | null;
  closed_reason: string | null;
  expires_at: string;
};

export type PriceSheet = PriceSheetSummary & {
  items: PriceSheetItem[];
  snapshot_hash: string;
  signature_image: string | null;
  signer_ip: string | null;
  signer_user_agent: string | null;
};

// ---- Admin ----

export function sendForApproval(supplierId: number, deliveryDate: string): Promise<PriceSheet> {
  return apiFetch("/price-approvals/admin", {
    method: "POST",
    body: JSON.stringify({ supplier_id: supplierId, delivery_date: deliveryDate }),
  });
}

export function fetchAdminSheets(params?: {
  deliveryDate?: string;
  supplierId?: number;
  status?: SheetStatus;
}): Promise<PriceSheetSummary[]> {
  const qs = new URLSearchParams();
  if (params?.deliveryDate) qs.set("delivery_date", params.deliveryDate);
  if (params?.supplierId) qs.set("supplier_id", String(params.supplierId));
  if (params?.status) qs.set("status", params.status);
  const query = qs.toString();
  return apiFetch(`/price-approvals/admin${query ? `?${query}` : ""}`);
}

export function fetchAdminSheet(id: number): Promise<PriceSheet> {
  return apiFetch(`/price-approvals/admin/${id}`);
}

export function withdrawSheet(id: number): Promise<PriceSheet> {
  return apiFetch(`/price-approvals/admin/${id}/withdraw`, { method: "POST" });
}

export function fetchAdminAttentionCount(): Promise<{ count: number }> {
  return apiFetch("/price-approvals/admin/attention-count");
}

// ---- Supplier ----

export function fetchMySheets(): Promise<PriceSheetSummary[]> {
  return apiFetch("/price-approvals/mine");
}

export function fetchMySheet(id: number): Promise<PriceSheet> {
  return apiFetch(`/price-approvals/mine/${id}`);
}

export function fetchMyPendingCount(): Promise<{ count: number }> {
  return apiFetch("/price-approvals/mine/pending-count");
}

export function approveSheet(
  id: number,
  body: { snapshot_hash: string; signer_name: string; signature_image: string; password: string; agreed: boolean }
): Promise<PriceSheet> {
  return apiFetch(`/price-approvals/mine/${id}/approve`, { method: "POST", body: JSON.stringify(body) });
}

export function rejectSheet(id: number, body: { snapshot_hash: string; reason: string }): Promise<PriceSheet> {
  return apiFetch(`/price-approvals/mine/${id}/reject`, { method: "POST", body: JSON.stringify(body) });
}
