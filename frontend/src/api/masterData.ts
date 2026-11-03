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
  // MANUAL (typed by Admin) or AUTO (Auto-generate); null when blank.
  selling_price_source: "MANUAL" | "AUTO" | null;
  // What branches currently see (published by the Master Data Team).
  published_selling_price: number | null;
  computed_gp_percent: number | null;
  keells_price: number | null;
  keells_price_date: string | null;
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

export function downloadMasterData(): Promise<void> {
  return downloadExcel("/master-data/export", "master-data-sheet.xlsx");
}

async function downloadExcel(path: string, fallbackName: string): Promise<void> {
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const access = localStorage.getItem("spar_access_token");
  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    headers: access ? { Authorization: `Bearer ${access}` } : {},
  });
  if (!res.ok) {
    throw new Error("Could not download the master data sheet.");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : fallbackName;

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

export type AutoGenerateSummary = {
  total_products: number;
  generated: number;
  preserved: number;
  without_price: number;
};

export function autoGenerateSellingPrices(): Promise<AutoGenerateSummary> {
  return apiFetch("/master-data/auto-generate-selling-prices", { method: "POST" });
}

export type MasterDataSendResult = {
  version: number;
  sent_at: string;
  product_count: number;
  products_with_price: number;
  created: boolean;
  emailed_to: string | null;
  email_error: string | null;
};

/** Admin: make the current sheet the latest version for the Master Data Team. */
export function sendToMasterData(): Promise<MasterDataSendResult> {
  return apiFetch("/master-data/send", { method: "POST" });
}

export type PublishSummary = {
  version: number;
  published_at: string;
  products_updated: number;
  products_unchanged: number;
  branches_updated: number;
  skipped_missing_price: string[];
  skipped_invalid: string[];
};

export type MasterDataSubmission = {
  version: number;
  sent_at: string;
  sent_by: string;
  product_count: number;
  products_with_price: number;
  published_at: string | null;
  published_by: string | null;
  publish_summary: PublishSummary | null;
  sheet: MasterDataSheet;
};

/** Master Data Team: the latest sheet Admin sent. Rejects with a 404 ApiError before the first send. */
export function fetchTeamSheet(): Promise<MasterDataSubmission> {
  return apiFetch("/master-data/team");
}

export function downloadTeamSheet(): Promise<void> {
  return downloadExcel("/master-data/team/export", "SPAR-Master-Data-Sheet.xlsx");
}

/** Master Data Team: Update Selling Prices — every branch sees the sheet's selling prices. */
export function publishSellingPrices(): Promise<PublishSummary> {
  return apiFetch("/master-data/team/publish", { method: "POST" });
}

export type CostPriceItem = {
  product_id: number;
  product_code: string;
  pos_code: string;
  description: string;
  category_name: string;
  cost_price: number;
  price_date: string | null;
};

export type SupplierCostPrices = {
  supplier_name: string;
  items: CostPriceItem[];
};

export type CostPrices = {
  version: number;
  sent_at: string;
  suppliers: SupplierCostPrices[];
  skipped_no_pos_code: string[];
};

/** Master Data Team: Cost Price column of the latest sent sheet, by supplier. 404 before the first send. */
export function fetchTeamCostPrices(): Promise<CostPrices> {
  return apiFetch("/master-data/team/cost-prices");
}

/** One POS-import Excel file per supplier, all in one .zip. */
export function downloadTeamCostPricesZip(): Promise<void> {
  return downloadExcel("/master-data/team/cost-prices/zip", "SPAR-Cost-Prices.zip");
}

export type SellingPriceItem = {
  product_id: number;
  product_code: string;
  pos_code: string;
  description: string;
  category_name: string;
  selling_price: number;
  published_selling_price: number | null;
};

export type SellingPrices = {
  version: number;
  sent_at: string;
  items: SellingPriceItem[];
  skipped_no_pos_code: string[];
  without_selling_price: number;
};

/** Master Data Team: Selling Price column of the latest sent sheet. 404 before the first send. */
export function fetchTeamSellingPrices(): Promise<SellingPrices> {
  return apiFetch("/master-data/team/selling-prices");
}

/** One POS-import Excel file (code + selling price). */
export function downloadTeamSellingPricesExcel(): Promise<void> {
  return downloadExcel("/master-data/team/selling-prices/excel", "SPAR-Selling-Prices.xlsx");
}
