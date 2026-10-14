import { apiFetch } from "./client";

export type Settings = {
  branch_order_deadline: string;
  supplier_price_deadline: string;
  // Suppliers approve/reject SPAR's adjusted prices by this time on the submission day.
  supplier_approval_deadline: string;
  // Weekdays suppliers may submit prices on, comma-separated, Monday=0 .. Sunday=6 (e.g. "0,2,4").
  supplier_price_days: string;
  support_phone: string;
};

export function fetchSettings(): Promise<Settings> {
  return apiFetch("/settings");
}

export function updateSetting(key: keyof Settings, value: string): Promise<Settings> {
  return apiFetch(`/settings/${key}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

// Kept separate from Settings above: this one is admin-only and isn't part
// of the public GET /settings payload.
export type MasterDataEmail = { master_data_email: string };

export function fetchMasterDataEmail(): Promise<MasterDataEmail> {
  return apiFetch("/settings/master-data-email");
}

export function updateMasterDataEmail(value: string): Promise<MasterDataEmail> {
  return apiFetch("/settings/master-data-email", {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

// ---- Notification emails (Admin only) ----

export type EmailLogEntry = {
  id: number;
  kind: string;
  recipient: string;
  subject: string;
  status: "SENT" | "FAILED" | "SKIPPED";
  error: string | null;
  created_at: string;
};

export type EmailStatus = {
  configured: boolean;
  provider: "Brevo" | "SMTP" | null;
  from_address: string | null;
  admin_recipients: string[];
  suppliers_without_email: string[];
  recent: EmailLogEntry[];
};

export function fetchEmailStatus(): Promise<EmailStatus> {
  return apiFetch("/settings/email-status");
}

export function sendTestEmail(): Promise<{ status: "SENT" | "FAILED" | "SKIPPED" }> {
  return apiFetch("/settings/email-test", { method: "POST" });
}
