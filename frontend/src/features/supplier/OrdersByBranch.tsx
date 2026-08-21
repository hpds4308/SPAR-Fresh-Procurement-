import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { MySupplierOrders, downloadMySupplierOrders, fetchMySupplierOrders } from "../../api/supplierOrders";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { IconBranches } from "../shared/Icons";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

type ProductRow = {
  product_id: number;
  product_code: string;
  description: string;
  category_name: string;
  unit_code: string;
  costPrice: number | null;
  costPriceIsEstimated: boolean;
  costPriceAsOf: string | null;
  quantitiesByBranch: Record<number, number>;
  total: number;
};

export default function OrdersByBranch() {
  const [data, setData] = useState<MySupplierOrders | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  // Set right before the auto-select below triggers a second render with a
  // new selectedDate — lets the effect recognize "this date change was just
  // us echoing back data we already have" and skip a redundant re-fetch.
  const autoSelecting = useRef(false);

  useEffect(() => {
    if (autoSelecting.current) {
      autoSelecting.current = false;
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchMySupplierOrders(selectedDate)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(null);
        if (!selectedDate && d.delivery_date) {
          autoSelecting.current = true;
          setSelectedDate(d.delivery_date);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load your orders.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDate]);

  // Pivot the branch-grouped data into rows-by-product, columns-by-branch —
  // same shape as the supplier's own spreadsheet: one row per item, one
  // column per store, quantity in the cell where that store ordered it.
  const { branches, rows, branchTotals, grandQty } = useMemo(() => {
    const branchList = data?.branches ?? [];
    const productMap = new Map<number, ProductRow>();

    for (const branch of branchList) {
      for (const item of branch.items) {
        if (!productMap.has(item.product_id)) {
          productMap.set(item.product_id, {
            product_id: item.product_id,
            product_code: item.product_code,
            description: item.product_description,
            category_name: item.category_name,
            unit_code: item.unit_code,
            costPrice: null,
            costPriceIsEstimated: false,
            costPriceAsOf: null,
            quantitiesByBranch: {},
            total: 0,
          });
        }
        const row = productMap.get(item.product_id)!;
        row.quantitiesByBranch[branch.branch_id] = item.quantity;
        row.total += item.quantity;
        if (row.costPrice === null && item.effective_price !== null) {
          row.costPrice = item.effective_price;
          row.costPriceIsEstimated = item.price_is_estimated;
          row.costPriceAsOf = item.price_as_of;
        }
      }
    }

    const rows = Array.from(productMap.values()).sort(
      (a, b) => a.category_name.localeCompare(b.category_name) || a.description.localeCompare(b.description)
    );

    const branchTotals: Record<number, number> = {};
    for (const branch of branchList) {
      branchTotals[branch.branch_id] = rows.reduce((sum, r) => sum + (r.quantitiesByBranch[branch.branch_id] ?? 0), 0);
    }
    const grandQty = rows.reduce((sum, r) => sum + r.total, 0);

    return { branches: branchList.map((b) => ({ branch_id: b.branch_id, branch_name: b.branch_name })), rows, branchTotals, grandQty };
  }, [data]);

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      await downloadMySupplierOrders(selectedDate);
    } catch {
      setError("Could not download the file. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  if (loading && !data) {
    return (
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        <SkeletonTable rows={6} columns={4} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">
        {error}
      </div>
    );
  }

  if (!data || data.available_delivery_dates.length === 0) {
    return (
      <EmptyState
        icon={<IconBranches width={20} height={20} />}
        title="No orders yet"
        description="Once Admin places an order with you, it will appear here grouped by branch."
      />
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
      <div className="p-4 border-b border-sage-100 flex flex-wrap items-center gap-3">
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
        <span className="text-xs text-crate-800/40">
          {branches.length} store{branches.length === 1 ? "" : "s"} · {rows.length} item{rows.length === 1 ? "" : "s"}
        </span>
        <span className="ml-auto text-sm font-semibold text-crate-800">
          Order value: Rs. {data.grand_total.toFixed(2)}
        </span>
        <button
          onClick={handleDownload}
          disabled={downloading || rows.length === 0}
          className="text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-4 py-1.5 font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
        >
          {downloading ? "Preparing…" : "Download Excel"}
        </button>
      </div>

      {rows.some((r) => r.costPriceIsEstimated) && (
        <p className="px-4 pt-3 text-xs text-mango-600/80">
          <span className="font-medium">Amber</span> cost prices are estimated from an earlier submission — this
          supplier hasn't submitted a price for this exact delivery date yet.
        </p>
      )}

      {error && <p className="text-tomato-600 text-sm px-4 pt-3">{error}</p>}

      {rows.length === 0 ? (
        <p className="p-6 text-sm text-crate-800/35 text-center">No orders for this order date.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm border-collapse">
            <thead>
              <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
                <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 0, width: 90, minWidth: 90 }}>
                  Product Code
                </th>
                <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 90, width: 90, minWidth: 90 }}>
                  Category
                </th>
                <th
                  className="text-left px-3 py-2.5 sticky z-20 bg-sage-50 shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                  style={{ left: 180, width: 200, minWidth: 200 }}
                >
                  Description
                </th>
                <th className="text-right px-3 py-2.5 whitespace-nowrap">Cost Price</th>
                <th className="text-center px-3 py-2 bg-mango-500/15 text-crate-800/70" colSpan={branches.length}>
                  Store wise Order Qty
                </th>
                <th className="text-right px-3 py-2.5 whitespace-nowrap">Total</th>
              </tr>
              <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide border-b border-sage-200">
                <th className="sticky z-20 bg-sage-50" style={{ left: 0, width: 90 }}></th>
                <th className="sticky z-20 bg-sage-50" style={{ left: 90, width: 90 }}></th>
                <th
                  className="sticky z-20 bg-sage-50 shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                  style={{ left: 180, width: 200 }}
                ></th>
                <th></th>
                {branches.map((b) => (
                  <th key={b.branch_id} className="text-right px-3 py-1.5 bg-mango-500/15 whitespace-nowrap font-medium">
                    {b.branch_name}
                  </th>
                ))}
                <th></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sage-100">
              {rows.map((row) => (
                <tr key={row.product_id} className="hover:bg-sage-50/50 transition-colors duration-100">
                  <td className="px-3 py-2 text-crate-800/50 sticky z-10 bg-white" style={{ left: 0, width: 90 }}>
                    {row.product_code}
                  </td>
                  <td className="px-3 py-2 sticky z-10 bg-white" style={{ left: 90, width: 90 }}>
                    <CategoryBadge name={row.category_name} />
                  </td>
                  <td
                    className="px-3 py-2 text-crate-950 sticky z-10 bg-white shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                    style={{ left: 180, width: 200 }}
                  >
                    {row.description}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {row.costPrice !== null ? (
                      <div className="flex flex-col items-end">
                        <span className={row.costPriceIsEstimated ? "text-mango-600/90" : "text-crate-800/70"}>
                          Rs. {row.costPrice.toFixed(2)}
                        </span>
                        {row.costPriceIsEstimated && (
                          <span className="text-[10px] text-mango-600/70 leading-none mt-0.5">
                            est. {row.costPriceAsOf ? `from ${new Date(row.costPriceAsOf + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })}` : ""}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-crate-800/20">—</span>
                    )}
                  </td>
                  {branches.map((b) => {
                    const qty = row.quantitiesByBranch[b.branch_id];
                    return (
                      <td
                        key={b.branch_id}
                        className={`px-3 py-2 text-right ${
                          qty !== undefined ? "bg-tomato-500/10 font-medium text-crate-950" : "text-crate-800/20"
                        }`}
                      >
                        {qty !== undefined ? qty : ""}
                      </td>
                    );
                  })}
                  <td className="px-3 py-2 text-right font-semibold text-crate-950">{row.total}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-sage-50 font-semibold text-crate-800 border-t border-sage-200">
                <td className="px-3 py-2.5 sticky z-10 bg-sage-50" style={{ left: 0, width: 90 }}></td>
                <td className="px-3 py-2.5 sticky z-10 bg-sage-50" style={{ left: 90, width: 90 }}></td>
                <td
                  className="px-3 py-2.5 sticky z-10 bg-sage-50 shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                  style={{ left: 180, width: 200 }}
                >
                  Total
                </td>
                <td></td>
                {branches.map((b) => (
                  <td key={b.branch_id} className="px-3 py-2.5 text-right">
                    {branchTotals[b.branch_id]}
                  </td>
                ))}
                <td className="px-3 py-2.5 text-right">{grandQty}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
