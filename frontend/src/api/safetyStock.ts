import { apiFetch } from "./client";

export type SafetyStock = {
  // product_id -> quantity; a missing product_id means none set.
  quantities: Record<number, number>;
  updated_at: string | null;
  updated_by_username: string | null;
};

export function fetchMySafetyStock(): Promise<SafetyStock> {
  return apiFetch("/safety-stock/mine");
}

// Replaces the branch's whole list — an empty `lines` clears everything.
export function saveMySafetyStock(lines: { product_id: number; quantity: number }[]): Promise<SafetyStock> {
  return apiFetch("/safety-stock/mine", {
    method: "PUT",
    body: JSON.stringify({ lines }),
  });
}
