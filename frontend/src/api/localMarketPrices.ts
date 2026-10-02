import { apiFetch } from "./client";

// HARTI daily bulletin prices — see backend harti_import_service.py.

export type MarketKey = "dambulla" | "thambuththegama" | "keppetipola" | "nuwara_eliya";

export const MARKETS: { key: MarketKey; label: string }[] = [
  { key: "dambulla", label: "Dambulla" },
  { key: "thambuththegama", label: "Thambuththegama" },
  { key: "keppetipola", label: "Keppetipola" },
  { key: "nuwara_eliya", label: "Nuwara Eliya" },
];

export type MarketRange = {
  min: number;
  max: number;
  // The market's midpoint, (min + max) / 2.
  average: number;
};

export type LocalMarketPrice = {
  dc_code: string;
  system_name: string;
  // The product's label in the HARTI bulletin.
  pdf_name: string;
  product_id: number | null;
  category_name: string | null;
  // Mean of the markets that have a price that day.
  final_average: number;
} & Record<MarketKey, MarketRange | null>;

export type LocalMarketReport = {
  // null only when nothing has ever been imported.
  report_date: string | null;
  imported_at: string | null;
  // Newest first.
  available_dates: string[];
  rows: LocalMarketPrice[];
};

export type LocalMarketImportResult = {
  report_date: string;
  saved: number;
  // Mapped products in the bulletin with no price in any of the four markets.
  not_priced: string[];
  // Saved, but their DC code has no product in the system.
  unmatched: { dc_code: string; system_name: string }[];
};

// Omit reportDate for the newest imported bulletin.
export function fetchLocalMarketPrices(reportDate?: string): Promise<LocalMarketReport> {
  return apiFetch(`/local-market-prices${reportDate ? `?report_date=${reportDate}` : ""}`);
}

// Downloads HARTI's newest English bulletin server-side right now and
// replaces that report date's prices with it.
export function syncLocalMarketPrices(): Promise<LocalMarketImportResult> {
  return apiFetch("/local-market-prices/sync", { method: "POST" });
}

// Fallback when harti.gov.lk can't be reached: Admin downloads the
// bulletin PDF themselves and uploads it here.
export function uploadLocalMarketBulletin(file: File): Promise<LocalMarketImportResult> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch("/local-market-prices/upload", { method: "POST", body });
}

export async function downloadLocalMarketExcel(reportDate: string): Promise<void> {
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const access = localStorage.getItem("spar_access_token");
  const res = await fetch(`${API_BASE}/api/v1/local-market-prices/export?report_date=${reportDate}`, {
    headers: access ? { Authorization: `Bearer ${access}` } : {},
  });
  if (!res.ok) {
    throw new Error("Could not download the local market prices.");
  }
  const blob = await res.blob();
  // Same "YYYY.MM.DD.xlsx" name the backend sends — set here too because
  // a cross-origin response doesn't expose Content-Disposition.
  const filename = `${reportDate.split("-").join(".")}.xlsx`;

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
