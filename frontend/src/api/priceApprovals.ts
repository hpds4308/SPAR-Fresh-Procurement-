import { apiFetch } from "./client";

// Stored statuses, plus EXPIRED — a PENDING sheet whose delivery date has
// arrived. PARTIAL: the supplier approved some items and rejected the rest.
// See backend price_approval_service.py.
export type SheetStatus = "PENDING" | "APPROVED" | "PARTIAL" | "REJECTED" | "VOIDED" | "WITHDRAWN" | "EXPIRED";

export type ItemDecision = "APPROVED" | "REJECTED";

// Row-level status on the price tables: no adjustment (null), DRAFT (not
// sent), the status of the sheet it was sent on, or — once the supplier
// has answered — that item's own APPROVED/REJECTED.
export type RowApprovalStatus = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | null;

export type PriceSheetItem = {
  supplier_price_id: number;
  product_id: number;
  product_code: string;
  product_description: string;
  unit_code: string;
  supplier_price: number;
  adjusted_price: number;
  // The supplier's answer, once they've responded. counter_price is the
  // final price they gave for a rejected item (null: their own price applies).
  decision: ItemDecision | null;
  counter_price: number | null;
  // SPAR's final offer on an item the supplier already rejected once:
  // approve or reject only, no new price. Rejecting keeps previous_price
  // (the final price they gave last time; null = their submitted price).
  final_offer: boolean;
  previous_price: number | null;
};

export type PriceSheetSummary = {
  id: number;
  supplier_id: number;
  supplier_name: string;
  delivery_date: string;
  status: SheetStatus;
  item_count: number;
  approved_count: number;
  rejected_count: number;
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

export function respondToSheet(
  id: number,
  body: {
    snapshot_hash: string;
    items: { supplier_price_id: number; decision: ItemDecision; counter_price?: number | null }[];
    note?: string | null;
    agreed: boolean;
    signature_image?: string | null;
  }
): Promise<PriceSheet> {
  return apiFetch(`/price-approvals/mine/${id}/respond`, { method: "POST", body: JSON.stringify(body) });
}
