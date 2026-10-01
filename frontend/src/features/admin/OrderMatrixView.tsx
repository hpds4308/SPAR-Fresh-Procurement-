import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import {
  AutoSubmittedOrder,
  OrderMatrix,
  autoSubmitDescription,
  fetchOrderMatrix,
  downloadOrderMatrix,
  fetchUnreviewedAutoOrders,
  reviewAutoOrders,
} from "../../api/orders";
import ProductAssignmentPanel from "./ProductAssignmentPanel";
import AdminAddOrderItemModal from "./AdminAddOrderItemModal";
import { CategoryBadge } from "../shared/ui/CategoryBadge";

type AddItemTarget = {
  branchId: number;
  branchName: string;
  productId: number;
  productDescription: string;
  unitCode: string;
  currentQuantity: number | null;
};

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

const AUTO_POLL_MS = 60000;

export default function OrderMatrixView({
  onAutoOrdersChanged,
}: {
  onAutoOrdersChanged?: (count: number) => void;
} = {}) {
  const [matrix, setMatrix] = useState<OrderMatrix | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [hideEmpty, setHideEmpty] = useState(true);
  const [openProductId, setOpenProductId] = useState<number | null>(null);
  const [addItemTarget, setAddItemTarget] = useState<AddItemTarget | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  // Orders the system auto-submitted for branches that missed the cutoff,
  // still waiting for Admin to acknowledge them.
  const [autoOrders, setAutoOrders] = useState<AutoSubmittedOrder[]>([]);
  const [reviewing, setReviewing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let seen: Set<number> | null = null;
    function poll() {
      fetchUnreviewedAutoOrders()
        .then((list) => {
          if (cancelled) return;
          setAutoOrders(list);
          onAutoOrdersChanged?.(list.length);
          // A new auto-submitted order changes the matrix itself — reload it.
          if (seen && list.some((o) => !seen!.has(o.order_id))) setRefreshKey((k) => k + 1);
          seen = new Set(list.map((o) => o.order_id));
        })
        .catch(() => {});
    }
    poll();
    const id = setInterval(poll, AUTO_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function markReviewed(orderId?: number) {
    setReviewing(true);
    try {
      await reviewAutoOrders(orderId !== undefined ? { order_id: orderId } : {});
      const remaining = orderId !== undefined ? autoOrders.filter((o) => o.order_id !== orderId) : [];
      setAutoOrders(remaining);
      onAutoOrdersChanged?.(remaining.length);
      setRefreshKey((k) => k + 1);
    } catch {
      setError("Could not mark the order as reviewed. Please try again.");
    } finally {
      setReviewing(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchOrderMatrix(selectedDate)
      .then((data) => {
        if (!cancelled) {
          setMatrix(data);
          if (!selectedDate) setSelectedDate(data.delivery_date);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the order matrix.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDate, refreshKey]);

  const visibleRows = useMemo(() => {
    if (!matrix) return [];
    if (!hideEmpty) return matrix.rows;
    return matrix.rows.filter((r) => Object.keys(r.quantities).length > 0);
  }, [matrix, hideEmpty]);

  async function handleDownload() {
    setDownloading(true);
    try {
      await downloadOrderMatrix(selectedDate);
    } catch {
      setError("Could not download the file. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  if (loading && !matrix) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-8 text-crate-800/40 text-sm text-center">
        Loading orders…
      </div>
    );
  }

  if (error && !matrix) {
    return (
      <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">
        {error}
      </div>
    );
  }

  if (matrix && matrix.available_delivery_dates.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-8 text-crate-800/40 text-sm text-center">
        No branch orders have been submitted yet.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
      <div className="p-4 border-b border-sage-100 flex flex-wrap items-center gap-3 justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-crate-800/70">Order Date</label>
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="border border-sage-300 bg-sage-50/60 rounded-full px-3.5 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-200"
          >
            {matrix?.available_delivery_dates.map((d) => (
              <option key={d} value={d}>
                {formatDate(d)}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-sm text-crate-800/70 ml-1">
            <input
              type="checkbox"
              checked={hideEmpty}
              onChange={(e) => setHideEmpty(e.target.checked)}
              className="accent-crate-700"
            />
            Hide products with no orders
          </label>
          <span className="text-xs text-crate-800/35 ml-1">
            Click a product row to assign suppliers &middot; click a branch's quantity to add or edit an item for that branch
          </span>
        </div>
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-4 py-1.5 font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
        >
          {downloading ? "Preparing…" : "Download Excel"}
        </button>
      </div>

      {error && <p className="text-tomato-600 text-sm px-4 pt-3">{error}</p>}

      {autoOrders.length > 0 && (
        <div className="m-4 rounded-xl border border-mango-500/40 bg-mango-500/10 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[#8A5A0D]">
                {autoOrders.length} order{autoOrders.length === 1 ? " was" : "s were"} auto-submitted
              </p>
              <p className="text-xs text-crate-800/60 mt-0.5">
                These branches didn't submit before the cutoff, so the system submitted an order for them. Check the
                quantities, adjust if needed, then mark as reviewed.
              </p>
            </div>
            {autoOrders.length > 1 && (
              <button
                onClick={() => markReviewed()}
                disabled={reviewing}
                className="text-xs font-semibold rounded-full border border-mango-500/60 text-[#8A5A0D] px-3 py-1 hover:bg-mango-500/15 disabled:opacity-50 transition-colors duration-150"
              >
                Mark all reviewed
              </button>
            )}
          </div>
          <ul className="mt-3 divide-y divide-mango-500/20">
            {autoOrders.map((o) => (
              <li key={o.order_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                <span className="font-medium text-crate-950">{o.branch_name}</span>
                <span className="text-xs text-crate-800/60">
                  Delivery {formatDate(o.delivery_date)} &middot; {o.line_count} item{o.line_count === 1 ? "" : "s"}
                </span>
                <span className="text-xs text-crate-800/50 basis-full sm:basis-auto">{autoSubmitDescription(o)}</span>
                <span className="ml-auto flex gap-2">
                  {o.delivery_date !== selectedDate && (
                    <button
                      onClick={() => setSelectedDate(o.delivery_date)}
                      className="text-xs font-medium text-crate-700 hover:underline"
                    >
                      View
                    </button>
                  )}
                  <button
                    onClick={() => markReviewed(o.order_id)}
                    disabled={reviewing}
                    className="text-xs font-semibold rounded-full bg-white border border-mango-500/60 text-[#8A5A0D] px-3 py-1 hover:bg-mango-500/15 disabled:opacity-50 transition-colors duration-150"
                  >
                    Mark reviewed
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
              <th
                className="text-left px-3 py-2.5 sticky z-20 bg-sage-50"
                style={{ left: 0, width: 100, minWidth: 100 }}
              >
                Category
              </th>
              <th
                className="text-left px-3 py-2.5 sticky z-20 bg-sage-50"
                style={{ left: 100, width: 90, minWidth: 90 }}
              >
                Code
              </th>
              <th
                className="text-left px-3 py-2.5 sticky z-20 bg-sage-50 shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                style={{ left: 190, width: 220, minWidth: 220 }}
              >
                Product
              </th>
              {matrix?.branches.map((b) => (
                <th
                  key={b.branch_id}
                  className={`text-right px-3 py-2.5 whitespace-nowrap ${b.auto_submitted ? "bg-mango-500/10" : ""}`}
                  title={b.auto_submitted ? autoSubmitDescription(b) : undefined}
                >
                  {b.branch_name}
                  {b.auto_submitted && (
                    <span
                      className={`ml-1.5 inline-block align-middle rounded-full px-1.5 py-0.5 text-[10px] font-bold normal-case tracking-normal ${
                        b.auto_reviewed ? "bg-sage-100 text-crate-800/60" : "bg-mango-500/25 text-[#8A5A0D]"
                      }`}
                    >
                      Auto
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-sage-100">
            {visibleRows.map((row) => (
              <tr
                key={row.product_id}
                className="hover:bg-sage-50/70 group cursor-pointer transition-colors duration-100"
                onClick={() => setOpenProductId(row.product_id)}
              >
                <td
                  className="px-3 py-2 sticky z-10 bg-white group-hover:bg-sage-50/70"
                  style={{ left: 0, width: 100, minWidth: 100 }}
                >
                  <CategoryBadge name={row.category_name} />
                </td>
                <td
                  className="px-3 py-2 text-crate-800/40 sticky z-10 bg-white group-hover:bg-sage-50/70"
                  style={{ left: 100, width: 90, minWidth: 90 }}
                >
                  {row.product_code}
                </td>
                <td
                  className="px-3 py-2 text-crate-950 sticky z-10 bg-white group-hover:bg-sage-50/70 shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                  style={{ left: 190, width: 220, minWidth: 220 }}
                >
                  {row.description}
                </td>
                {matrix?.branches.map((b) => {
                  const qty = row.quantities[String(b.branch_id)];
                  return (
                    <td
                      key={b.branch_id}
                      className={`px-3 py-2 text-right text-crate-800/80 hover:bg-mango-500/15 cursor-pointer transition-colors duration-100 ${
                        b.auto_submitted ? "bg-mango-500/5" : ""
                      }`}
                      title={`Click to ${qty !== undefined ? "edit" : "add"} ${b.branch_name}'s quantity`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setAddItemTarget({
                          branchId: b.branch_id,
                          branchName: b.branch_name,
                          productId: row.product_id,
                          productDescription: row.description,
                          unitCode: row.unit_code,
                          currentQuantity: qty !== undefined ? qty : null,
                        });
                      }}
                    >
                      {qty !== undefined ? qty : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {visibleRows.length === 0 && (
          <p className="text-crate-800/35 text-sm px-4 py-8 text-center">No products match the current filter.</p>
        )}
      </div>

      {openProductId !== null && selectedDate && (
        <ProductAssignmentPanel
          productId={openProductId}
          deliveryDate={selectedDate}
          onClose={() => setOpenProductId(null)}
          onSaved={() => setRefreshKey((k) => k + 1)}
        />
      )}

      {addItemTarget && selectedDate && (
        <AdminAddOrderItemModal
          branchId={addItemTarget.branchId}
          branchName={addItemTarget.branchName}
          productId={addItemTarget.productId}
          productDescription={addItemTarget.productDescription}
          unitCode={addItemTarget.unitCode}
          deliveryDate={selectedDate}
          currentQuantity={addItemTarget.currentQuantity}
          hasExistingOrderForDate={
            matrix?.rows.some((r) => r.quantities[String(addItemTarget.branchId)] !== undefined) ?? false
          }
          onClose={() => setAddItemTarget(null)}
          onSaved={() => setRefreshKey((k) => k + 1)}
        />
      )}
    </div>
  );
}
