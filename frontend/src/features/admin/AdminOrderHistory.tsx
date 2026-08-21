import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { Order, OrderSummary, fetchOrder, fetchOrderDates, fetchOrdersForDate } from "../../api/orders";
import EmptyState from "../shared/EmptyState";
import { StatusBadge } from "../shared/ui/Badge";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { IconChevronLeft, IconChevronRight, IconClock } from "../shared/Icons";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function statusTone(status: string): "warning" | "info" | "success" | "neutral" {
  switch (status) {
    case "SUBMITTED":
      return "warning";
    case "ASSIGNED":
      return "info";
    case "CONFIRMED":
      return "success";
    default:
      return "neutral";
  }
}

export default function AdminOrderHistory() {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [datesLoading, setDatesLoading] = useState(true);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedDetail, setExpandedDetail] = useState<Order | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    fetchOrderDates()
      .then((d) => {
        setDates(d);
        if (d.length > 0) setSelectedDate(d[0]);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load order history."))
      .finally(() => setDatesLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    setOrdersLoading(true);
    setError(null);
    setExpandedId(null);
    fetchOrdersForDate(selectedDate)
      .then((data) => {
        if (!cancelled) setOrders(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load orders for this date.");
      })
      .finally(() => {
        if (!cancelled) setOrdersLoading(false);
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

  async function toggleExpand(orderId: number) {
    if (expandedId === orderId) {
      setExpandedId(null);
      setExpandedDetail(null);
      return;
    }
    setExpandedId(orderId);
    setExpandedDetail(null);
    setDetailLoading(true);
    try {
      const detail = await fetchOrder(orderId);
      setExpandedDetail(detail);
    } catch {
      setError("Could not load that order's details.");
    } finally {
      setDetailLoading(false);
    }
  }

  const totalItems = useMemo(() => orders.reduce((sum, o) => sum + o.line_count, 0), [orders]);

  if (datesLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-8 text-crate-800/40 text-sm text-center">
        Loading order history…
      </div>
    );
  }

  if (dates.length === 0) {
    return (
      <EmptyState
        icon={<IconClock width={20} height={20} />}
        title="No order history yet"
        description="Once branches start placing orders, you'll be able to browse them here day by day."
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
          {orders.length} branch order{orders.length === 1 ? "" : "s"} · {totalItems} item{totalItems === 1 ? "" : "s"} total
        </span>
      </div>

      {error && <p className="text-tomato-600 text-sm px-1">{error}</p>}

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        {ordersLoading ? (
          <SkeletonTable rows={6} columns={4} />
        ) : orders.length === 0 ? (
          <p className="text-sm text-crate-800/40 text-center py-10">No branch orders on this date.</p>
        ) : (
          <div className="divide-y divide-sage-100">
            {orders.map((o, i) => (
              <div
                key={o.id}
                className="motion-safe:animate-fade-up"
                style={{ animationDuration: "0.3s", animationDelay: `${Math.min(i, 12) * 25}ms`, animationFillMode: "backwards" }}
              >
                <button
                  onClick={() => toggleExpand(o.id)}
                  className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-sage-50/50 transition-colors duration-100"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-sm font-medium text-crate-950 truncate">{o.branch_name}</span>
                    <StatusBadge tone={statusTone(o.status)}>{o.status}</StatusBadge>
                  </div>
                  <span className="text-xs text-crate-800/40 shrink-0 ml-3">
                    {o.line_count} item{o.line_count === 1 ? "" : "s"}
                  </span>
                </button>

                {expandedId === o.id && (
                  <div className="px-5 pb-4 bg-sage-50/40">
                    {detailLoading ? (
                      <p className="text-xs text-crate-800/40 py-2">Loading items…</p>
                    ) : expandedDetail ? (
                      <table className="w-full text-sm mt-1">
                        <thead>
                          <tr className="text-crate-800/40 text-left text-xs uppercase tracking-wide">
                            <th className="pb-1.5 font-medium">Product</th>
                            <th className="pb-1.5 font-medium text-right">Quantity</th>
                            <th className="pb-1.5 font-medium text-right">Unit</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-sage-200/60">
                          {expandedDetail.lines.map((l) => (
                            <tr key={l.id}>
                              <td className="py-1.5 text-crate-950">{l.product_description}</td>
                              <td className="py-1.5 text-right text-crate-800/80">{l.quantity}</td>
                              <td className="py-1.5 text-right text-crate-800/40">{l.unit_code}</td>
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
