import { apiFetch } from "./client";

export type DailyReportRow = {
  delivery_date: string;
  orders_count: number;
  assigned_orders_count: number;
  branches_count: number;
  spend: number;
};

export type SupplierSpendRow = {
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  spend: number;
  lines_count: number;
};

export type CategorySpendRow = {
  category_name: string;
  spend: number;
  lines_count: number;
};

export type TopProductRow = {
  product_id: number;
  product_code: string;
  description: string;
  category_name: string;
  unit_code: string;
  total_quantity: number;
  total_spend: number;
  order_count: number;
};

export type ReportTotals = {
  total_orders: number;
  assigned_orders: number;
  fulfillment_rate: number;
  total_spend: number;
  days_count: number;
};

export type AdminReport = {
  start_date: string;
  end_date: string;
  totals: ReportTotals;
  daily: DailyReportRow[];
  by_supplier: SupplierSpendRow[];
  by_category: CategorySpendRow[];
  top_products: TopProductRow[];
};

export function fetchAdminReport(startDate?: string, endDate?: string): Promise<AdminReport> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiFetch(`/reports/admin/summary${qs}`);
}

export function reportExportUrl(startDate?: string, endDate?: string): string {
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return `${API_BASE}/api/v1/reports/admin/summary/export${qs}`;
}

export async function downloadReport(startDate?: string, endDate?: string): Promise<void> {
  const access = localStorage.getItem("spar_access_token");
  const res = await fetch(reportExportUrl(startDate, endDate), {
    headers: access ? { Authorization: `Bearer ${access}` } : {},
  });
  if (!res.ok) {
    throw new Error("Could not download the report.");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "report.xlsx";

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
