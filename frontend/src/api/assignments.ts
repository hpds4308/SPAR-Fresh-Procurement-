import { apiFetch } from "./client";

export type SupplierQuote = {
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  price: number;
  unit_code: string;
};

export type AssignmentEntry = {
  supplier_id: number;
  quantity: number;
  agreed_price: number;
};

export type ProductComparison = {
  product_id: number;
  product_code: string;
  description: string;
  unit_code: string;
  delivery_date: string;
  total_demand: number;
  quotes: SupplierQuote[];
  assignments: AssignmentEntry[];
  assigned_quantity: number;
  fully_assigned: boolean;
};

export function fetchProductComparison(productId: number, deliveryDate: string): Promise<ProductComparison> {
  return apiFetch(`/orders/admin/product/${productId}/comparison?delivery_date=${deliveryDate}`);
}

export function setProductAssignments(
  productId: number,
  deliveryDate: string,
  assignments: { supplier_id: number; quantity: number; agreed_price: number }[]
): Promise<ProductComparison> {
  return apiFetch(`/orders/admin/product/${productId}/assignments?delivery_date=${deliveryDate}`, {
    method: "PUT",
    body: JSON.stringify({ assignments }),
  });
}

export type MyAssignmentLine = {
  product_id: number;
  product_code: string;
  description: string;
  unit_code: string;
  quantity: number;
  agreed_price: number;
  line_total: number;
};

export type MyAssignments = {
  delivery_date: string | null;
  lines: MyAssignmentLine[];
  grand_total: number;
  available_delivery_dates: string[];
};

export function fetchMyAssignments(deliveryDate?: string): Promise<MyAssignments> {
  const qs = deliveryDate ? `?delivery_date=${deliveryDate}` : "";
  return apiFetch(`/assignments/mine${qs}`);
}
