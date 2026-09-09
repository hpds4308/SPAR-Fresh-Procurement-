import { apiFetch } from "./client";

export type MasterDataSupplierColumn = {
  supplier_id: number;
  supplier_name: string;
};

export type MasterDataRow = {
  product_id: number;
  product_code: string;
  pos_code: string | null;
  description: string;
  category_name: string;
  target_gp_percent: number;
  selling_price: number | null;
  computed_gp_percent: number | null;
  cost_price: number | null;
  cost_price_supplier_name: string | null;
  cost_price_date: string | null;
  supplier_prices: Record<number, number | null>;
};

export type MasterDataSheet = {
  suppliers: MasterDataSupplierColumn[];
  rows: MasterDataRow[];
};

export type MasterDataFieldName = "target_gp_percent" | "selling_price";

export function fetchMasterData(): Promise<MasterDataSheet> {
  return apiFetch("/master-data");
}

export function updateMasterDataField(
  productId: number,
  field: MasterDataFieldName,
  value: string | number | null
): Promise<MasterDataRow> {
  return apiFetch(`/master-data/${productId}`, {
    method: "PATCH",
    body: JSON.stringify({ field, value }),
  });
}

export async function downloadMasterData(): Promise<void> {
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const access = localStorage.getItem("spar_access_token");
  const res = await fetch(`${API_BASE}/api/v1/master-data/export`, {
    headers: access ? { Authorization: `Bearer ${access}` } : {},
  });
  if (!res.ok) {
    throw new Error("Could not download the master data sheet.");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "master-data-sheet.xlsx";

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export function sendMasterDataEmail(): Promise<{ sent_to: string }> {
  return apiFetch("/master-data/send-email", { method: "POST" });
}

export function autoGenerateSellingPrices(): Promise<{ updated: number }> {
  return apiFetch("/master-data/auto-generate-selling-prices", { method: "POST" });
}
