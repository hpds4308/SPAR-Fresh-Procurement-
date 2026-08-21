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
