import { apiFetch } from "./client";

export type PromotionType = "FRESH_CHOICE" | "SPECIAL_WEEKEND" | "SPECIAL";

export type Promotion = {
  product_id: number;
  promotion_type: PromotionType;
  start_date: string; // YYYY-MM-DD, inclusive
  end_date: string; // YYYY-MM-DD, inclusive
};

// Promotions running today — what branches see as labels.
export function fetchActivePromotions(): Promise<Promotion[]> {
  return apiFetch("/promotions/active");
}

// Admin only: every saved promotion, including upcoming and ended ones.
export function fetchAllPromotions(): Promise<Promotion[]> {
  return apiFetch("/promotions");
}

// Admin only: replaces the whole list — an empty list clears everything.
export function savePromotions(lines: Promotion[]): Promise<Promotion[]> {
  return apiFetch("/promotions", {
    method: "PUT",
    body: JSON.stringify({ lines }),
  });
}
