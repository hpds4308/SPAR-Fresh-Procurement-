import { useEffect, useState } from "react";
import { Promotion, fetchActivePromotions } from "../../api/promotions";

// Promotions running today, keyed by product_id. Labels are informational
// only, so a failed fetch just means no labels — it never blocks the page.
export function useActivePromotions(): Record<number, Promotion> {
  const [byProduct, setByProduct] = useState<Record<number, Promotion>>({});
  useEffect(() => {
    let cancelled = false;
    fetchActivePromotions()
      .then((list) => {
        if (cancelled) return;
        const next: Record<number, Promotion> = {};
        for (const p of list) next[p.product_id] = p;
        setByProduct(next);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return byProduct;
}
