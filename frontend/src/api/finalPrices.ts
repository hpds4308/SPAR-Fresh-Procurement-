import { apiFetch, apiFetchBlob } from "./client";

// SPAR's signature, stamped automatically on every supplier's final price list.
export type SparSignature = {
  signature_image: string | null;
  signatory_name: string | null;
  signatory_title: string | null;
  updated_at: string | null;
  updated_by_name: string | null;
};

export function fetchSparSignature(): Promise<SparSignature> {
  return apiFetch("/final-prices/signature");
}

export function saveSparSignature(body: {
  signatory_name: string;
  signatory_title: string | null;
  signature_image: string;
}): Promise<SparSignature> {
  return apiFetch("/final-prices/signature", { method: "PUT", body: JSON.stringify(body) });
}

export type FinalDates = {
  dates: string[];
  next_delivery_date: string | null;
  next_final_at: string | null;
  cutoff_label: string;
  signature_ready: boolean;
};

export type FinalPriceLine = {
  product_id: number;
  product_code: string;
  category: string;
  product_description: string;
  unit_code: string;
  your_price: number;
  adjusted_price: number | null;
  final_price: number;
  basis: string;
};

export type FinalPriceList = {
  supplier_name: string;
  delivery_date: string;
  finalized_at: string;
  reference: string;
  lines: FinalPriceLine[];
  spar_signature: SparSignature;
  supplier_signatures: {
    price_sheet_id: number;
    signer_name: string | null;
    signed_at: string | null;
    signature_image: string;
  }[];
};

export function fetchMyFinalDates(): Promise<FinalDates> {
  return apiFetch("/final-prices/mine/dates");
}

export function fetchMyFinalPrices(deliveryDate: string): Promise<FinalPriceList> {
  return apiFetch(`/final-prices/mine?delivery_date=${deliveryDate}`);
}

export async function downloadMyFinalPrices(
  deliveryDate: string,
  supplierName: string,
  format: "excel" | "pdf",
  fileDate: string = deliveryDate
): Promise<void> {
  const blob = await apiFetchBlob(`/final-prices/mine/${format}?delivery_date=${deliveryDate}`);
  // Built here too because a cross-origin response doesn't expose Content-Disposition.
  const safe = supplierName.replace(/[^A-Za-z0-9]/g, "-").replace(/^-+|-+$/g, "").toLowerCase() || "supplier";
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `spar-final-prices-${safe}-${fileDate}.${format === "excel" ? "xlsx" : "pdf"}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
