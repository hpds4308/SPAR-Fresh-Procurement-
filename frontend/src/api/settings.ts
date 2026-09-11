import { apiFetch } from "./client";

export type Settings = {
  branch_order_deadline: string;
  supplier_price_deadline: string;
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
