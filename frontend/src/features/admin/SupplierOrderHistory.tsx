import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import {
  SupplierOrderAdmin,
  SupplierOrderSummary,
  fetchSupplierOrderAdmin,
  fetchSupplierOrderDates,
  fetchSupplierOrderSummaries,
} from "../../api/supplierOrders";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { IconChevronLeft, IconChevronRight, IconClock } from "../shared/Icons";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

// Mirrors BranchOrderHistory.tsx exactly, pivoted around supplier instead
// of branch — same date navigation, same expand-to-see-lines pattern.
// Expanding a row reuses the existing admin supplier-order endpoint (the
// same one the Supplier Order Builder edits), so this view can never show
// a different total than that screen does for the same supplier/date.
export default function SupplierOrderHistory() {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<SupplierOrderSummary[]>([]);
  const [datesLoading, setDatesLoading] = useState(true);
  const [summariesLoading, setSummariesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedDetail, setExpandedDetail] = useState<SupplierOrderAdmin | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    fetchSupplierOrderDates()
      .then((d) => {
        setDates(d);
        if (d.length > 0) setSelectedDate(d[0]);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load supplier order history."))
      .finally(() => setDatesLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    setSummariesLoading(true);
    setError(null);
    setExpandedId(null);
    fetchSupplierOrderSummaries(selectedDate)
      .then((data) => {
        if (!cancelled) setSummaries(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load suppliers for this date.");
      })
      .finally(() => {
        if (!cancelled) setSummariesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDate]);

  const dateIndex = useMemo(
    () => (selectedDate ? dates.indexOf(selectedDate) : -1),
    [dates, selectedDate]
  );
  const hasPrevDay = dateIndex >= 0 && dateIndex < dates.length - 1; // dates sorted desc — "prev" = older = higher index
  const hasNextDay = dateIndex > 0; // "next" = more recent = lower index

  function goPrevDay() {
    if (hasPrevDay) setSelectedDate(dates[dateIndex + 1]);
  }
  function goNextDay() {
    if (hasNextDay) setSelectedDate(dates[dateIndex - 1]);
  }

  async function toggleExpand(supplierId: number) {
    if (expandedId === supplierId) {
      setExpandedId(null);
      setExpandedDetail(null);
      return;
    }
    setExpandedId(supplierId);
    setExpandedDetail(null);
    setDetailLoading(true);
    try {
      const detail = await fetchSupplierOrderAdmin(supplierId, selectedDate!);
      setExpandedDetail(detail);
    } catch {
      setError("Could not load that supplier's order details.");
    } finally {
      setDetailLoading(false);
    }
  }

  const totalItems = useMemo(() => summaries.reduce((sum, s) => sum + s.line_count, 0), [summaries]);
  const totalValue = useMemo(() => summaries.reduce((sum, s) => sum + s.total_value, 0), [summaries]);

  if (datesLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-8 text-crate-800/40 text-sm text-center">
        Loading supplier order history…
      </div>
    );
  }

  if (dates.length === 0) {
    return (
      <EmptyState
        icon={<IconClock width={20} height={20} />}
        title="No supplier order history yet"
        description="Once Admin gives orders to suppliers, you'll be able to browse them here day by day."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4 flex flex-wrap items-center gap-3">
        <button
          onClick={goPrevDay}
          disabled={!hasPrevDay}
          className="w-8 h-8 flex items-center justify-center rounded-full border border-sage-300 text-crate-800/60 hover:bg-sage-50 disabled:opacity-30 disabled:hover:bg-transparent transition-colors duration-150"
          aria-label="Previous day with orders"
        >
          <IconChevronLeft width={14} height={14} />
        </button>
        <button
          onClick={goNextDay}
          disabled={!hasNextDay}
          className="w-8 h-8 flex items-center justify-center rounded-full border border-sage-300 text-crate-800/60 hover:bg-sage-50 disabled:opacity-30 disabled:hover:bg-transparent transition-colors duration-150"
          aria-label="Next day with orders"
        >
          <IconChevronRight width={14} height={14} />
        </button>

        <select
          value={selectedDate ?? ""}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        >
          {dates.map((d) => (
            <option key={d} value={d}>
              {formatDate(d)}
            </option>
          ))}
        </select>

        <span className="text-xs text-crate-800/35 ml-auto">
          {summaries.length} supplier{summaries.length === 1 ? "" : "s"} · {totalItems} item{totalItems === 1 ? "" : "s"} · Rs.{" "}
          {totalValue.toFixed(2)} total
        </span>
      </div>

      {error && <p className="text-tomato-600 text-sm px-1">{error}</p>}

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        {summariesLoading ? (
          <SkeletonTable rows={6} columns={4} />
        ) : summaries.length === 0 ? (
          <p className="text-sm text-crate-800/40 text-center py-10">No supplier orders on this date.</p>
        ) : (
          <div className="divide-y divide-sage-100">
            {summaries.map((s, i) => (
              <div
                key={s.supplier_id}
                className="motion-safe:animate-fade-up"
                style={{ animationDuration: "0.3s", animationDelay: `${Math.min(i, 12) * 25}ms`, animationFillMode: "backwards" }}
              >
                <button
                  onClick={() => toggleExpand(s.supplier_id)}
                  className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-sage-50/50 transition-colors duration-100"
                >
                  <span className="text-sm font-medium text-crate-950 truncate">{s.supplier_name}</span>
                  <span className="text-xs text-crate-800/40 shrink-0 ml-3">
                    {s.line_count} item{s.line_count === 1 ? "" : "s"} · Rs. {s.total_value.toFixed(2)}
                  </span>
                </button>

                {expandedId === s.supplier_id && (
                  <div className="px-5 pb-4 bg-sage-50/40">
                    {detailLoading ? (
                      <p className="text-xs text-crate-800/40 py-2">Loading items…</p>
                    ) : expandedDetail ? (
                      <table className="w-full text-sm mt-1">
                        <thead>
                          <tr className="text-crate-800/40 text-left text-xs uppercase tracking-wide">
                            <th className="pb-1.5 font-medium">Branch</th>
                            <th className="pb-1.5 font-medium">Product</th>
                            <th className="pb-1.5 font-medium text-right">Quantity</th>
                            <th className="pb-1.5 font-medium text-right">Unit</th>
                            <th className="pb-1.5 font-medium text-right">Price</th>
                            <th className="pb-1.5 font-medium text-right">Total</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-sage-200/60">
                          {expandedDetail.items.map((it) => (
                            <tr key={it.id}>
                              <td className="py-1.5 text-crate-800/70">{it.branch_name}</td>
                              <td className="py-1.5 text-crate-950">{it.product_description}</td>
                              <td className="py-1.5 text-right text-crate-800/80">{it.quantity}</td>
                              <td className="py-1.5 text-right text-crate-800/40">{it.unit_code}</td>
                              <td className="py-1.5 text-right text-crate-800/70">
                                {it.effective_price !== null ? `Rs. ${it.effective_price.toFixed(2)}` : "—"}
                                {it.price_is_estimated && (
                                  <span className="text-[9px] text-mango-600 ml-1">est.</span>
                                )}
                              </td>
                              <td className="py-1.5 text-right text-crate-950 font-medium">
                                {it.line_total !== null ? `Rs. ${it.line_total.toFixed(2)}` : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : null}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
