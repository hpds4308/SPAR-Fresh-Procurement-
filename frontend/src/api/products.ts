import { apiFetch } from "./client";

// One row of the admin Product List — includes items that were removed.
export type AdminProduct = {
  id: number;
  product_code: string;
  pos_code: string | null;
  description: string;
  category_id: number;
  category_name: string;
  subcategory: string | null;
  unit_id: number;
  unit_code: string;
  status: "ACTIVE" | "INACTIVE" | string;
  created_at: string | null;
};

export type ProductOption = { id: number; name: string };
export type ProductOptions = { categories: ProductOption[]; units: ProductOption[] };

export type NewProduct = {
  product_code: string;
  pos_code: string | null;
  description: string;
  category_id: number;
  subcategory: string | null;
  unit_id: number;
};

// Admin only: every product, active and removed.
export function fetchAllProducts(): Promise<AdminProduct[]> {
  return apiFetch("/products/all");
}

// Admin only: categories and units to pick from when adding a product.
export function fetchProductOptions(): Promise<ProductOptions> {
  return apiFetch("/products/options");
}

// Admin only: adds a new product; branches can order it straight away.
export function createProduct(body: NewProduct): Promise<AdminProduct> {
  return apiFetch("/products", { method: "POST", body: JSON.stringify(body) });
}

// Admin only: takes a product off the list. Its order and price history is kept.
export function removeProduct(id: number): Promise<AdminProduct> {
  return apiFetch(`/products/${id}`, { method: "DELETE" });
}

// Admin only: puts a removed product back on the list.
export function restoreProduct(id: number): Promise<AdminProduct> {
  return apiFetch(`/products/${id}/restore`, { method: "POST" });
}
