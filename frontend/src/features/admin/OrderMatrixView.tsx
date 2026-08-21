import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { OrderMatrix, fetchOrderMatrix, downloadOrderMatrix } from "../../api/orders";
import ProductAssignmentPanel from "./ProductAssignmentPanel";
import { CategoryBadge } from "../shared/ui/CategoryBadge";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

export default function OrderMatrixView() {
  const [matrix, setMatrix] = useState<OrderMatrix | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [hideEmpty, setHideEmpty] = useState(true);
  const [openProductId, setOpenProductId] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

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
          <span className="text-xs text-crate-800/35 ml-1">Click a product row to assign suppliers</span>
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
                <th key={b.branch_id} className="text-right px-3 py-2.5 whitespace-nowrap">
                  {b.branch_name}
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
                    <td key={b.branch_id} className="px-3 py-2 text-right text-crate-800/80">
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
    </div>
  );
}
