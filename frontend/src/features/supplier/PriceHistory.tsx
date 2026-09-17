import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { SupplierPrice, fetchMyPrices, fetchPriceWindow } from "../../api/pricing";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { IconTag } from "../shared/Icons";

export default function PriceHistory({ refreshKey }: { refreshKey: number }) {
  const [prices, setPrices] = useState<SupplierPrice[]>([]);
  const [deliveryDate, setDeliveryDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const window_ = await fetchPriceWindow();
        if (cancelled) return;
        setDeliveryDate(window_.delivery_date);
        const data = await fetchMyPrices(window_.delivery_date);
        if (!cancelled) setPrices(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load prices.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
        <SkeletonTable rows={6} columns={3} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">
        {error}
      </div>
    );
  }

  if (prices.length === 0) {
    return (
      <EmptyState
        icon={<IconTag width={20} height={20} />}
        title="No prices submitted yet"
        description={deliveryDate ? `Submit your prices for delivery on ${deliveryDate} from the Submit Prices tab.` : undefined}
      />
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6">
      <p className="text-sm text-crate-800/60 mb-3">Prices submitted for delivery on {deliveryDate}</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-crate-800/40 text-left text-xs uppercase tracking-wide">
            <th className="pb-2 font-medium">Product</th>
            <th className="pb-2 font-medium text-right">Your Price</th>
            <th className="pb-2 font-medium text-right">Admin Adjusted Price</th>
            <th className="pb-2 font-medium text-right">Unit</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-sage-100">
          {prices.map((p, i) => (
            <tr
              key={p.id}
              className="motion-safe:animate-fade-up"
              style={{ animationDuration: "0.3s", animationDelay: `${Math.min(i, 12) * 25}ms`, animationFillMode: "backwards" }}
            >
              <td className="py-2 text-crate-950">{p.product_description}</td>
              <td className="py-2 text-right text-crate-800/80">Rs. {p.price.toFixed(2)}</td>
              <td className="py-2 text-right">
                {p.adjusted_price !== null ? (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="font-semibold text-crate-950">Rs. {p.adjusted_price.toFixed(2)}</span>
                    <span className="text-[10px] uppercase tracking-wide bg-crate-700 text-white rounded-full px-2 py-0.5 font-semibold">
                      SPAR Fresh Procurement
                    </span>
                  </span>
                ) : (
                  <span className="text-crate-800/25">—</span>
                )}
              </td>
              <td className="py-2 text-right text-crate-800/40">{p.unit_code}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
