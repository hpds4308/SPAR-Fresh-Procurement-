import { useEffect, useState } from "react";
import { Promotion, fetchActivePromotions } from "../../api/promotions";

// Promotions running today, keyed by product_id, shared by every label on
// the page so a screen full of products makes one request, not one per
// row. Refetched when it's older than STALE_MS (so a long-open page picks
// up Admin's changes) or right away after Admin saves/deletes promotions.
// Labels are informational only, so a failed fetch just means no labels —
// it never blocks the page.

type ByProduct = Record<number, Promotion>;

const STALE_MS = 60_000;

let current: ByProduct = {};
let fetchedAt = 0;
let inFlight: Promise<void> | null = null;
const listeners = new Set<(next: ByProduct) => void>();

function load() {
  if (inFlight) return;
  inFlight = fetchActivePromotions()
    .then((list) => {
      const next: ByProduct = {};
      for (const p of list) next[p.product_id] = p;
      current = next;
      fetchedAt = Date.now();
      listeners.forEach((l) => l(current));
    })
    .catch(() => {})
    .finally(() => {
      inFlight = null;
    });
}

// Call after Admin changes promotions so every label updates at once.
export function refreshActivePromotions() {
  fetchedAt = 0;
  load();
}

export function useActivePromotions(): ByProduct {
  const [byProduct, setByProduct] = useState<ByProduct>(current);
  useEffect(() => {
    listeners.add(setByProduct);
    setByProduct(current);
    if (Date.now() - fetchedAt > STALE_MS) load();
    return () => {
      listeners.delete(setByProduct);
    };
  }, []);
  return byProduct;
}
