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
