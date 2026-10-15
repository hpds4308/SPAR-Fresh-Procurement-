import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { compareProductDisplayOrder } from "../../api/orders";
import { AdminSupplierPrice, fetchAllPrices } from "../../api/pricing";
import { Supplier, fetchSuppliers } from "../../api/suppliers";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { IconTag } from "../shared/Icons";
import { ProductPromotion } from "../shared/ui/PromotionBadge";

const RANGE_PRESETS = [
  { label: "2 weeks", days: 14 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
];

// Local calendar date, not toISOString() — that converts to UTC, which in
// Sri Lanka (UTC+5:30) turns local midnight into the previous day.
function localISO(d: Date): string {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
function daysFromTodayISO(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return localISO(d);
}
function formatShort(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

// The price the supplier is actually paid, by the same rule as their Final
// Prices list: an adjusted price they approved, else their own final price
// for an item they rejected, else the price they submitted.
function agreedPrice(r: AdminSupplierPrice): number {
  if (r.approval_status === "APPROVED" && r.adjusted_price !== null) return r.adjusted_price;
  if (r.counter_price !== null) return r.counter_price;
  return r.price;
}

type Row = {
  key: string;
  product_id: number;
  product_code: string;
  product_description: string;
  category_name: string;
  supplier_name: string;
  byDate: Map<string, AdminSupplierPrice>;
};

export default function AdminSupplierPriceHistory() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplierId, setSupplierId] = useState<number | "">("");
  // Delivery dates run a few days ahead of submission, so the default range
  // reaches a week forward to include the current cycle.
  const [startDate, setStartDate] = useState(daysFromTodayISO(-13));
  const [endDate, setEndDate] = useState(daysFromTodayISO(7));
  const [prices, setPrices] = useState<AdminSupplierPrice[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSuppliers().then(setSuppliers).catch(() => {});
  }, []);

  useEffect(() => {
    if (!startDate || !endDate || startDate > endDate) return;
    let cancelled = false;
    setLoading(true);
    fetchAllPrices({ startDate, endDate, supplierId: supplierId || undefined })
      .then((data) => {
        if (!cancelled) {
          setPrices(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load supplier price history.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [startDate, endDate, supplierId]);

  // Only delivery dates someone actually quoted for — suppliers price for
  // delivery days, not every calendar day.
  const dates = useMemo(() => Array.from(new Set(prices.map((p) => p.delivery_date))).sort(), [prices]);

  const rows = useMemo(() => {
    const byKey = new Map<string, Row>();
    for (const p of prices) {
      const key = `${p.product_id}-${p.supplier_id}`;
      let row = byKey.get(key);
      if (!row) {
        row = {
          key,
          product_id: p.product_id,
          product_code: p.product_code,
          product_description: p.product_description,
          category_name: p.category_name,
          supplier_name: p.supplier_name,
          byDate: new Map(),
        };
        byKey.set(key, row);
      }
      row.byDate.set(p.delivery_date, p);
    }
    return Array.from(byKey.values()).sort(
      (a, b) =>
        compareProductDisplayOrder(
          { category_name: a.category_name, description: a.product_description },
          { category_name: b.category_name, description: b.product_description }
        ) || a.supplier_name.localeCompare(b.supplier_name)
    );
  }, [prices]);

  const categories = useMemo(() => Array.from(new Set(rows.map((r) => r.category_name))).sort(), [rows]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows
      .filter((r) => (category ? r.category_name === category : true))
      .filter((r) =>
        q
          ? r.product_description.toLowerCase().includes(q) ||
            r.product_code.toLowerCase().includes(q) ||
            r.supplier_name.toLowerCase().includes(q)
          : true
      );
  }, [rows, search, category]);

  const allSuppliers = supplierId === "";

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4 flex flex-wrap items-center gap-3">
        <select
          value={supplierId}
          onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : "")}
          className="border border-sage-300 bg-sage-50/60 rounded-full px-3.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        >
          <option value="">All suppliers</option>
          {suppliers.map((s) => (
            <option key={s.id} value={s.id}>
              {s.supplier_name}
            </option>
          ))}
        </select>
        <span className="text-sage-300">|</span>
        {RANGE_PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => {
              setStartDate(daysFromTodayISO(-(p.days - 1)));
              setEndDate(daysFromTodayISO(7));
            }}
            className="text-sm px-3 py-1.5 rounded-full bg-sage-100 text-crate-800 font-medium hover:bg-sage-200 transition-colors duration-150"
          >
            Last {p.label}
          </button>
        ))}
        <input
          type="date"
          value={startDate}
          max={endDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="border border-sage-300 rounded-full px-3 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30"
        />
        <span className="text-crate-800/50 text-sm">to</span>
        <input
          type="date"
          value={endDate}
          min={startDate}
          onChange={(e) => setEndDate(e.target.value)}
          className="border border-sage-300 rounded-full px-3 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30"
        />
        <input
          type="text"
          placeholder={allSuppliers ? "Search item, code or supplier…" : "Search item or code…"}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[10rem] border border-sage-300 bg-sage-50/60 rounded-full px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="border border-sage-300 bg-sage-50/60 rounded-full px-3.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      <p className="text-xs text-crate-800/50">
        Each cell is the price for that delivery date: SPAR's adjusted price if the supplier approved it, their own
        final price if they rejected it with one, otherwise the price they submitted. A struck-out figure is the
        price originally submitted.{allSuppliers && " A shaded cell is the lowest submitted price for the item on that date."}
      </p>

      {error && <p className="text-tomato-600 text-sm">{error}</p>}

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        {loading ? (
          <SkeletonTable rows={8} columns={6} />
        ) : filteredRows.length === 0 ? (
          <EmptyState
            icon={<IconTag width={20} height={20} />}
            title="No supplier prices in this range"
            description="Try a wider date range or another supplier."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm border-collapse">
              <thead>
                <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
                  <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 0, width: 90, minWidth: 90 }}>
                    Code
                  </th>
                  <th
                    className="text-left px-3 py-2.5 sticky z-20 bg-sage-50 shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                    style={{ left: 90, width: 200, minWidth: 200 }}
                  >
                    Description
                  </th>
                  <th className="text-left px-3 py-2.5 whitespace-nowrap">Category</th>
                  {allSuppliers && <th className="text-left px-3 py-2.5 whitespace-nowrap">Supplier</th>}
                  {dates.map((d) => (
                    <th key={d} className="text-right px-3 py-2.5 whitespace-nowrap font-medium">
                      {formatShort(d)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sage-100">
                {filteredRows.map((r) => (
                  <tr key={r.key} className="hover:bg-sage-50/50 transition-colors duration-100">
                    <td className="px-3 py-2 text-crate-800/50 sticky z-10 bg-white" style={{ left: 0, width: 90 }}>
                      {r.product_code}
                    </td>
                    <td
                      className="px-3 py-2 text-crate-950 sticky z-10 bg-white shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                      style={{ left: 90, width: 200 }}
                    >
                      {r.product_description}
                      <ProductPromotion productId={r.product_id} className="ml-1.5" />
                    </td>
                    <td className="px-3 py-2">
                      <CategoryBadge name={r.category_name} />
                    </td>
                    {allSuppliers && <td className="px-3 py-2 text-crate-800 whitespace-nowrap">{r.supplier_name}</td>}
                    {dates.map((d) => {
                      const p = r.byDate.get(d);
                      if (!p) {
                        return (
                          <td key={d} className="px-3 py-2 text-right text-crate-800/20">
                            —
                          </td>
                        );
                      }
                      const agreed = agreedPrice(p);
                      return (
                        <td
                          key={d}
                          className={`px-3 py-2 text-right whitespace-nowrap ${
                            allSuppliers && p.is_lowest_for_product ? "bg-crate-700/5" : ""
                          }`}
                        >
                          <div className="text-crate-950 font-medium">Rs. {agreed.toFixed(2)}</div>
                          {agreed !== p.price && (
                            <div className="text-[11px] text-crate-800/40 line-through">Rs. {p.price.toFixed(2)}</div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
