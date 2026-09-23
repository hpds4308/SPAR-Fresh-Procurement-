import { apiFetch } from "./client";

export type PriceWindow = {
  is_open: boolean;
  delivery_date: string;
  cutoff_time: string;
  server_time: string;
  // Delivery date of the most recently opened Mon/Wed/Fri submission cycle —
  // use this (not delivery_date) to default an admin browse view so it lands
  // on the cycle that's actually live.
  current_cycle_delivery_date: string;
};

export type SupplierPrice = {
  id: number;
  product_id: number;
  product_code: string;
  product_description: string;
  unit_code: string;
  price: number;
  delivery_date: string;
  adjusted_price: number | null;
};

export function fetchPriceWindow(): Promise<PriceWindow> {
  return apiFetch("/pricing/window");
}

export function fetchMyPrices(deliveryDate?: string): Promise<SupplierPrice[]> {
  const qs = deliveryDate ? `?delivery_date=${deliveryDate}` : "";
  return apiFetch(`/pricing/mine${qs}`);
}

export function submitPrices(prices: { product_id: number; price: number }[]): Promise<SupplierPrice[]> {
  return apiFetch("/pricing", {
    method: "POST",
    body: JSON.stringify({ prices }),
  });
}

export type LastPrice = {
  product_id: number;
  price: number;
  delivery_date: string;
};

export function fetchLastPrices(): Promise<LastPrice[]> {
  return apiFetch("/pricing/mine/last");
}

export type ReferencePrice = {
  product_id: number;
  source: string;
  price: number;
  delivery_date: string;
};

export function fetchReferencePrices(deliveryDate: string, source = "KEELLS"): Promise<ReferencePrice[]> {
  return apiFetch(`/pricing/reference?delivery_date=${deliveryDate}&source=${source}`);
}

export function fetchLastReferencePrices(source = "KEELLS"): Promise<ReferencePrice[]> {
  return apiFetch(`/pricing/reference/last?source=${source}`);
}

export function fetchReferencePriceHistory(
  startDate: string,
  endDate: string,
  source = "KEELLS"
): Promise<ReferencePrice[]> {
  return apiFetch(`/pricing/reference/history?start_date=${startDate}&end_date=${endDate}&source=${source}`);
}

export function setReferencePrice(
  productId: number,
  deliveryDate: string,
  price: number | null,
  source = "KEELLS"
): Promise<ReferencePrice | null> {
  return apiFetch(`/pricing/reference/${productId}?delivery_date=${deliveryDate}&source=${source}`, {
    method: "PUT",
    body: JSON.stringify({ price }),
  });
}

export type KeellsSyncResult = {
  delivery_date: string;
  matched: number;
  saved: number;
  skipped_rows: number;
  unmatched: { dc_code: string; system_name: string | null }[];
};

// Triggers an immediate server-side Keells scrape (launches a headless
// browser and re-reads keellssuper.com directly) instead of waiting for
// the daily scheduled worker. Replaces every existing KEELLS price for
// deliveryDate with what this run finds — the Keells Price page is
// sync-only, there's no manual entry to merge on top of. Can take up to
// ~60s since it's a real page-by-page scrape.
export function syncKeellsPrices(deliveryDate: string): Promise<KeellsSyncResult> {
  return apiFetch(`/pricing/reference/keells-sync?delivery_date=${deliveryDate}`, {
    method: "POST",
  });
}

export type AdminSupplierPrice = {
  id: number;
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  product_id: number;
  product_code: string;
  product_description: string;
  category_name: string;
  unit_code: string;
  price: number;
  adjusted_price: number | null;
  sent_to_supplier: boolean;
  delivery_date: string;
  is_lowest_for_product: boolean;
  // Next distinct price tier below the lowest (null if fewer than two
  // distinct prices exist yet for this product) — ties at the lowest
  // price don't count as a second tier, see the backend for why.
  second_lowest_price: number | null;
  is_second_lowest_for_product: boolean;
};

export function fetchAllPrices(params?: {
  deliveryDate?: string;
  supplierId?: number;
  productId?: number;
}): Promise<AdminSupplierPrice[]> {
  const qs = new URLSearchParams();
  if (params?.deliveryDate) qs.set("delivery_date", params.deliveryDate);
  if (params?.supplierId) qs.set("supplier_id", String(params.supplierId));
  if (params?.productId) qs.set("product_id", String(params.productId));
  const query = qs.toString();
  return apiFetch(`/pricing/admin${query ? `?${query}` : ""}`);
}

export function setAdjustedPrice(
  priceId: number,
  adjustedPrice: number | null
): Promise<{ id: number; price: number; adjusted_price: number | null; sent_to_supplier: boolean }> {
  return apiFetch(`/pricing/admin/${priceId}/adjust`, {
    method: "PATCH",
    body: JSON.stringify({ adjusted_price: adjustedPrice }),
  });
}

export function sendAdjustedPrice(
  priceId: number
): Promise<{ id: number; adjusted_price: number | null; sent_to_supplier: boolean }> {
  return apiFetch(`/pricing/admin/${priceId}/send`, { method: "POST" });
}

export function unsendAdjustedPrice(
  priceId: number
): Promise<{ id: number; adjusted_price: number | null; sent_to_supplier: boolean }> {
  return apiFetch(`/pricing/admin/${priceId}/unsend`, { method: "POST" });
}
