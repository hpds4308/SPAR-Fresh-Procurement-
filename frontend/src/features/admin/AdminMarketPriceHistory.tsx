import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { compareProductDisplayOrder, fetchProducts, Product } from "../../api/orders";
import { ReferencePrice, fetchReferencePriceHistory } from "../../api/pricing";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { IconChart } from "../shared/Icons";

type Source = "KEELLS" | "LOCAL_MARKET";

const RANGE_PRESETS = [
  { label: "7 days", days: 7 },
  { label: "14 days", days: 14 },
  { label: "30 days", days: 30 },
];

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
function daysAgoISO(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}
function formatShort(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export default function AdminMarketPriceHistory() {
  const [source, setSource] = useState<Source>("KEELLS");
  const [startDate, setStartDate] = useState(daysAgoISO(6));
  const [endDate, setEndDate] = useState(todayISO());
  const [products, setProducts] = useState<Product[]>([]);
  const [rows, setRows] = useState<ReferencePrice[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchProducts()
      .then(setProducts)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load products."));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchReferencePriceHistory(startDate, endDate, source)
      .then((data) => {
        if (!cancelled) {
          setRows(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load price history.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [startDate, endDate, source]);

  const dates = useMemo(() => {
    const out: string[] = [];
    const d = new Date(startDate + "T00:00:00");
    const end = new Date(endDate + "T00:00:00");
    while (d <= end) {
      out.push(d.toISOString().slice(0, 10));
      d.setDate(d.getDate() + 1);
    }
    return out;
  }, [startDate, endDate]);

  const priceByProductAndDate = useMemo(() => {
    const map = new Map<number, Map<string, number>>();
    for (const r of rows) {
      if (!map.has(r.product_id)) map.set(r.product_id, new Map());
      map.get(r.product_id)!.set(r.delivery_date, r.price);
    }
    return map;
  }, [rows]);

  const categories = useMemo(() => Array.from(new Set(products.map((p) => p.category_name))).sort(), [products]);

  const filteredProducts = useMemo(() => {
    const q = search.trim().toLowerCase();
    return products
      .filter((p) => (category ? p.category_name === category : true))
      .filter((p) => (q ? p.description.toLowerCase().includes(q) || p.product_code.toLowerCase().includes(q) : true))
      .filter((p) => priceByProductAndDate.has(p.id))
      .sort(compareProductDisplayOrder);
  }, [products, search, category, priceByProductAndDate]);

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4 flex flex-wrap items-center gap-3">
        <div className="flex gap-1 bg-sage-100 rounded-full p-0.5 w-fit">
          {(["KEELLS", "LOCAL_MARKET"] as Source[]).map((s) => (
            <button
              key={s}
              onClick={() => setSource(s)}
              className={`text-xs font-semibold rounded-full px-4 py-1.5 transition-colors duration-150 ${
                source === s ? "bg-white text-crate-950 shadow-sm" : "text-crate-800/50 hover:text-crate-800"
              }`}
            >
              {s === "KEELLS" ? "Keells" : "Local Market"}
            </button>
          ))}
        </div>
        <span className="text-sage-300">|</span>
        {RANGE_PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => {
              setEndDate(todayISO());
              setStartDate(daysAgoISO(p.days - 1));
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
          max={todayISO()}
          onChange={(e) => setEndDate(e.target.value)}
          className="border border-sage-300 rounded-full px-3 py-1.5 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30"
        />
        <input
          type="text"
          placeholder="Search item or code…"
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

      {error && <p className="text-tomato-600 text-sm">{error}</p>}

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        {loading ? (
          <SkeletonTable rows={8} columns={6} />
        ) : filteredProducts.length === 0 ? (
          <EmptyState
            icon={<IconChart width={20} height={20} />}
            title="No prices recorded in this range"
            description="Enter prices from the Keells Prices or Local Market Prices page — they'll show up here as a trend."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm border-collapse">
              <thead>
                <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
                  <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 0, width: 90, minWidth: 90 }}>
                    Code
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
                  {dates.map((d) => (
                    <th key={d} className="text-right px-3 py-2.5 whitespace-nowrap font-medium">
                      {formatShort(d)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sage-100">
                {filteredProducts.map((p) => (
                  <tr key={p.id} className="hover:bg-sage-50/50 transition-colors duration-100">
                    <td className="px-3 py-2 text-crate-800/50 sticky z-10 bg-white" style={{ left: 0, width: 90 }}>
                      {p.product_code}
                    </td>
                    <td className="px-3 py-2 sticky z-10 bg-white" style={{ left: 90, width: 90 }}>
                      <CategoryBadge name={p.category_name} />
                    </td>
                    <td
                      className="px-3 py-2 text-crate-950 sticky z-10 bg-white shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                      style={{ left: 180, width: 200 }}
                    >
                      {p.description}
                    </td>
                    {dates.map((d) => {
                      const price = priceByProductAndDate.get(p.id)?.get(d);
                      return (
                        <td key={d} className={`px-3 py-2 text-right ${price !== undefined ? "text-crate-950 font-medium" : "text-crate-800/20"}`}>
                          {price !== undefined ? `Rs. ${price.toFixed(2)}` : "—"}
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
