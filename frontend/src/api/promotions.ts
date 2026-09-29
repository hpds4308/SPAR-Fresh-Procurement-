import { apiFetch } from "./client";

export type PromotionColor = "blue" | "green" | "yellow" | "red" | "purple" | "orange" | "pink" | "teal";

// A promotion Admin has created, e.g. "Fresh Choice" in blue.
export type PromotionType = {
  id: number;
  name: string;
  color: PromotionColor;
  product_count: number; // products it's currently set on
};

export type Promotion = {
  product_id: number;
  promotion_type_id: number;
  promotion_name: string;
  color: PromotionColor;
  start_date: string; // YYYY-MM-DD, inclusive
  end_date: string; // YYYY-MM-DD, inclusive
};

export type PromotionLine = Pick<Promotion, "product_id" | "promotion_type_id" | "start_date" | "end_date">;

// Promotions running today — what branches see as labels.
export function fetchActivePromotions(): Promise<Promotion[]> {
  return apiFetch("/promotions/active");
}

// Admin only: every promotion that has been created.
export function fetchPromotionTypes(): Promise<PromotionType[]> {
  return apiFetch("/promotions/types");
}

// Admin only: creates a new promotion.
export function createPromotionType(name: string, color: PromotionColor): Promise<PromotionType> {
  return apiFetch("/promotions/types", {
    method: "POST",
    body: JSON.stringify({ name, color }),
  });
}

// Admin only: deletes a promotion and removes it from every product.
export function deletePromotionType(id: number): Promise<null> {
  return apiFetch(`/promotions/types/${id}`, { method: "DELETE" });
}

// Admin only: every saved product promotion, including upcoming and ended ones.
export function fetchAllPromotions(): Promise<Promotion[]> {
  return apiFetch("/promotions");
}

// Admin only: replaces the whole list — an empty list clears everything.
export function savePromotions(lines: PromotionLine[]): Promise<Promotion[]> {
  return apiFetch("/promotions", {
    method: "PUT",
    body: JSON.stringify({ lines }),
  });
}
