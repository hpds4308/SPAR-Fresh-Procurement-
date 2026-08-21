import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { MyAssignments, fetchMyAssignments } from "../../api/assignments";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { IconCheckCircle } from "../shared/Icons";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

export default function ConfirmedOrders() {
  const [data, setData] = useState<MyAssignments | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchMyAssignments(selectedDate)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        if (!selectedDate && d.delivery_date) setSelectedDate(d.delivery_date);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load confirmed orders.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDate]);

  if (loading && !data) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
        <SkeletonTable rows={5} columns={4} />
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

  if (!data || data.available_delivery_dates.length === 0) {
    return (
      <EmptyState
        icon={<IconCheckCircle width={20} height={20} />}
        title="No confirmed orders yet"
        description="Once Admin assigns you a product, it will appear here with the agreed price."
      />
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
      <div className="p-4 border-b border-sage-100 flex items-center gap-3">
        <label className="text-sm text-crate-800/70">Order Date</label>
        <select
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="border border-sage-300 bg-sage-50/60 rounded-full px-3.5 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        >
          {data.available_delivery_dates.map((d) => (
            <option key={d} value={d}>
              {formatDate(d)}
            </option>
          ))}
        </select>
      </div>

      {data.lines.length === 0 ? (
        <p className="p-6 text-sm text-crate-800/35 text-center">No products confirmed for this date.</p>
      ) : (
        <div className="p-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-crate-800/40 text-left text-xs uppercase tracking-wide">
                <th className="pb-2 font-medium">Product</th>
                <th className="pb-2 font-medium text-right">Qty</th>
                <th className="pb-2 font-medium text-right">Unit</th>
                <th className="pb-2 font-medium text-right">Agreed price</th>
                <th className="pb-2 font-medium text-right">Line total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sage-100">
              {data.lines.map((ln) => (
                <tr key={ln.product_id}>
                  <td className="py-2 text-crate-950">{ln.description}</td>
                  <td className="py-2 text-right text-crate-800/80">{ln.quantity}</td>
                  <td className="py-2 text-right text-crate-800/40">{ln.unit_code}</td>
                  <td className="py-2 text-right text-crate-800/80">Rs. {ln.agreed_price.toFixed(2)}</td>
                  <td className="py-2 text-right text-crate-950 font-semibold">
                    Rs. {ln.line_total.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-sage-200">
                <td colSpan={4} className="pt-3 text-right text-sm font-medium text-crate-800/70">
                  Total
                </td>
                <td className="pt-3 text-right text-sm font-bold text-crate-950">
                  Rs. {data.grand_total.toFixed(2)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
