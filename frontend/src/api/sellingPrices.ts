import { apiFetch } from "./client";

export type SellingPriceRow = {
  product_id: number;
  product_code: string;
  pos_code: string | null;
  description: string;
  category_name: string;
  unit_code: string;
  selling_price: number | null; // null: nothing published for this item by that date
  published_at: string | null;
};

export type SellingPriceList = {
  on: string;
  rows: SellingPriceRow[];
};

/** Selling prices published by the Master Data Team, as they stood on `on` (YYYY-MM-DD; default today). */
export function fetchSellingPrices(on?: string): Promise<SellingPriceList> {
  return apiFetch(`/selling-prices${on ? `?on=${encodeURIComponent(on)}` : ""}`);
}
