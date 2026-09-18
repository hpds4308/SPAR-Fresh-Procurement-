import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { Order, OrderSummary, fetchMyOrders, fetchOrder, confirmDelivery } from "../../api/orders";
import EmptyState from "../shared/EmptyState";
import { IconBasket } from "../shared/Icons";
import { useToast } from "../shared/ui/Toast";

function statusColor(status: string): string {
  switch (status) {
    case "SUBMITTED":
      return "bg-mango-500/15 text-[#8A5A0D]";
    case "ASSIGNED":
      return "bg-crate-700/10 text-crate-800";
    case "CONFIRMED":
      return "bg-sage-200 text-crate-950";
    default:
      return "bg-sage-100 text-crate-800/60";
  }
}

function DeliveryConfirmForm({
  order,
  onConfirmed,
}: {
  order: Order;
  onConfirmed: (updated: Order) => void;
}) {
  const [received, setReceived] = useState<Record<number, string>>(
    Object.fromEntries(order.lines.map((ln) => [ln.product_id, String(ln.quantity)]))
  );
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setError(null);
    const lines = order.lines.map((ln) => ({
      product_id: ln.product_id,
      received_quantity: parseFloat(received[ln.product_id] ?? "0") || 0,
      notes: notes[ln.product_id]?.trim() || undefined,
    }));
    setSubmitting(true);
    try {
      const updated = await confirmDelivery(order.id, lines);
      onConfirmed(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not confirm delivery. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mt-3 border border-sage-200 rounded-xl p-4 bg-white">
      <p className="text-xs font-semibold uppercase tracking-wide text-crate-800/50 mb-3">
        Confirm what actually arrived
      </p>
      <div className="space-y-2">
        {order.lines.map((ln) => (
          <div key={ln.id} className="flex items-center gap-2 text-sm">
            <span className="flex-1 text-crate-950 truncate">{ln.product_description}</span>
            <span className="text-xs text-crate-800/40 w-24 text-right shrink-0">
              ordered {ln.quantity} {ln.unit_code}
            </span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={received[ln.product_id] ?? ""}
              onChange={(e) => setReceived((prev) => ({ ...prev, [ln.product_id]: e.target.value }))}
              className="w-20 border border-sage-300 rounded-full px-2 py-1 text-right text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30"
            />
            <span className="text-xs text-crate-800/40 w-8 shrink-0">{ln.unit_code}</span>
            <input
              type="text"
              placeholder="Note (optional)"
              value={notes[ln.product_id] ?? ""}
              onChange={(e) => setNotes((prev) => ({ ...prev, [ln.product_id]: e.target.value }))}
              className="w-32 border border-sage-300 rounded-full px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-crate-700/30"
            />
          </div>
        ))}
      </div>
      {error && <p className="text-tomato-600 text-sm mt-3">{error}</p>}
      <div className="flex justify-end mt-3">
        <button
          onClick={handleConfirm}
          disabled={submitting}
          className="text-sm bg-crate-700 text-white rounded-full px-4 py-1.5 font-medium hover:bg-crate-800 active:scale-[0.98] transition-all duration-150 disabled:opacity-50"
        >
          {submitting ? "Confirming…" : "Confirm Delivery"}
        </button>
      </div>
    </div>
  );
}

export default function OrderHistory({ refreshKey }: { refreshKey: number }) {
  const { show } = useToast();
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Order | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchMyOrders()
      .then((data) => {
        if (!cancelled) setOrders(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load orders.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  async function openOrder(id: number) {
    if (selected?.id === id) {
      setSelected(null);
      setConfirming(false);
      return;
    }
    setSelectedLoading(true);
    setConfirming(false);
    try {
      const order = await fetchOrder(id);
      setSelected(order);
    } catch {
      setError("Could not load that order's detail.");
    } finally {
      setSelectedLoading(false);
    }
  }

  function handleConfirmed(updated: Order) {
    setSelected(updated);
    setConfirming(false);
    setOrders((prev) => prev.map((o) => (o.id === updated.id ? { ...o, status: updated.status } : o)));
    show("success", "Delivery confirmed.");
  }

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-8 text-crate-800/40 text-sm text-center">
        Loading orders…
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

  if (orders.length === 0) {
    return (
      <EmptyState
        icon={<IconBasket width={20} height={20} />}
        title="No orders placed yet"
        description="Place your first order from the New Order tab — it'll show up here once submitted."
      />
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 divide-y divide-sage-100 overflow-hidden">
      {orders.map((o, i) => (
        <div
          key={o.id}
          className="px-6 py-4 motion-safe:animate-fade-up"
          style={{ animationDuration: "0.3s", animationDelay: `${Math.min(i, 12) * 25}ms`, animationFillMode: "backwards" }}
        >
          <button
            onClick={() => openOrder(o.id)}
            className="w-full flex items-center justify-between text-left group"
          >
            <div>
              <p className="text-sm text-crate-950 group-hover:text-crate-800">
                Order date {o.order_date} &middot; {o.line_count} item{o.line_count === 1 ? "" : "s"}
              </p>
              {o.has_admin_added_lines && (
                <p className="text-[11px] text-[#8A5A0D] font-medium mt-0.5">
                  Includes item(s) added by SPAR Fresh Procurement
                </p>
              )}
            </div>
            <span className={`text-xs px-2.5 py-1 rounded-full font-semibold ${statusColor(o.status)}`}>
              {o.status}
            </span>
          </button>

          {selected?.id === o.id && (
            <div className="mt-3 border border-sage-100 rounded-xl p-3 bg-sage-50">
              {selectedLoading ? (
                <p className="text-xs text-crate-800/40">Loading detail…</p>
              ) : (
                <>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-crate-800/40 text-left">
                        <th className="pb-1 font-medium">Product</th>
                        <th className="pb-1 font-medium text-right">Qty</th>
                        {selected.status === "CONFIRMED" && (
                          <th className="pb-1 font-medium text-right">Received</th>
                        )}
                        <th className="pb-1 font-medium text-right">Unit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.lines.map((ln) => {
                        const mismatch =
                          ln.received_quantity !== null && Math.abs(ln.received_quantity - ln.quantity) > 0.01;
                        return (
                          <tr key={ln.id} className={`text-crate-800/80 ${ln.added_by_admin ? "bg-mango-500/15" : ""}`}>
                            <td className="py-0.5">
                              {ln.product_description}
                              {ln.added_by_admin && (
                                <span className="block text-[10px] text-[#8A5A0D] font-medium">
                                  Ordered by SPAR Fresh Procurement
                                </span>
                              )}
                            </td>
                            <td className="py-0.5 text-right">{ln.quantity}</td>
                            {selected.status === "CONFIRMED" && (
                              <td className={`py-0.5 text-right ${mismatch ? "text-tomato-600 font-semibold" : ""}`}>
                                {ln.received_quantity ?? "—"}
                              </td>
                            )}
                            <td className="py-0.5 text-right">{ln.unit_code}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>

                  {selected.status === "CONFIRMED" && selected.confirmed_at && (
                    <p className="text-xs text-crate-800/40 mt-2">
                      Confirmed {new Date(selected.confirmed_at).toLocaleString()}
                      {selected.confirmed_by_username ? ` by ${selected.confirmed_by_username}` : ""}
                    </p>
                  )}

                  {selected.status === "ASSIGNED" && !confirming && (
                    <div className="flex justify-end mt-3">
                      <button
                        onClick={() => setConfirming(true)}
                        className="text-sm bg-crate-700 text-white rounded-full px-4 py-1.5 font-medium hover:bg-crate-800 active:scale-[0.98] transition-all duration-150"
                      >
                        Confirm Delivery
                      </button>
                    </div>
                  )}

                  {selected.status === "ASSIGNED" && confirming && (
                    <DeliveryConfirmForm order={selected} onConfirmed={handleConfirmed} />
                  )}
                </>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
