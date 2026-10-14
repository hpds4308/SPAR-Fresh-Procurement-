import { apiFetch } from "./client";

export type AdminAccount = {
  username: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
};

export type AdminAccountUpdate = {
  full_name: string;
  email: string;
  phone: string;
};

export function fetchAdminAccount(): Promise<AdminAccount> {
  return apiFetch("/users/me/account");
}

export function updateAdminAccount(payload: AdminAccountUpdate): Promise<AdminAccount> {
  return apiFetch("/users/me/account", { method: "PUT", body: JSON.stringify(payload) });
}
