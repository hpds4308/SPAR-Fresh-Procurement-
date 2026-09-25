import { apiFetch } from "./client";

export type Supplier = {
  id: number;
  supplier_code: string;
  supplier_name: string;
  status: string;
};

export type SupplierDetail = Supplier & {
  contact_person: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  company_number: string | null;
  whatsapp_number: string | null;
  account_updated_at: string | null;
};

export type SupplierAccountUpdate = {
  supplier_name: string;
  company_number: string;
  whatsapp_number: string;
  email: string;
};

export function fetchSuppliers(): Promise<Supplier[]> {
  return apiFetch("/suppliers");
}

export function fetchAllSuppliers(): Promise<SupplierDetail[]> {
  return apiFetch("/suppliers/all");
}

export function createSupplier(payload: {
  supplier_name: string;
  supplier_code?: string;
  contact_person?: string;
  phone?: string;
  email?: string;
  address?: string;
}): Promise<SupplierDetail> {
  return apiFetch("/suppliers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchMyAccount(): Promise<SupplierDetail> {
  return apiFetch("/suppliers/me/account");
}

export function updateMyAccount(payload: SupplierAccountUpdate): Promise<SupplierDetail> {
  return apiFetch("/suppliers/me/account", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}
