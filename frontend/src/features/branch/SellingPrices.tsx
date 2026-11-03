import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { SellingPriceList, fetchSellingPrices } from "../../api/sellingPrices";
import EmptyState from "../shared/EmptyState";
import { IconTag } from "../shared/Icons";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { ProductPromotion } from "../shared/ui/PromotionBadge";
import { SkeletonTable } from "../shared/ui/Skeleton";

// Today in Sri Lanka as YYYY-MM-DD (the date input's format).
function todayColombo(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Colombo" });
}

function formatPublished(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/**
 * Branch: the selling prices the Master Data Team published, read-only.
 * The date picker shows the prices that applied on that day.
 */
export default function SellingPrices() {
  const [date, setDate] = useState(todayColombo);
  const [data, setData] = useState<SellingPriceList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [pricedOnly, setPricedOnly] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchSellingPrices(date || undefined)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load selling prices.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [date]);

  const rows = data?.rows ?? [];
  const categories = useMemo(() => Array.from(new Set(rows.map((r) => r.category_name))), [rows]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (category && r.category_name !== category) return false;
      if (pricedOnly && r.selling_price === null) return false;
      if (!q) return true;
      return (
        r.description.toLowerCase().includes(q) ||
        r.product_code.toLowerCase().includes(q) ||
        (r.pos_code ?? "").toLowerCase().includes(q)
      );
    });
  }, [rows, search, category, pricedOnly]);
  const pricedCount = rows.filter((r) => r.selling_price !== null).length;

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search item, code, or POS code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[12rem] border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="border border-sage-300 bg-sage-50/60 rounded-full px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-crate-800/70">
          Date
          <input
            type="date"
            value={date}
            max={todayColombo()}
            onChange={(e) => setDate(e.target.value)}
            className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-crate-800/70 cursor-pointer">
          <input
            type="checkbox"
            checked={pricedOnly}
            onChange={(e) => setPricedOnly(e.target.checked)}
            className="accent-crate-700"
          />
          With a price only
        </label>
        <span className="text-xs text-crate-800/40">
          {filtered.length} of {rows.length} items · {pricedCount} priced
        </span>
      </div>

      {error && <p className="text-tomato-600 text-sm px-1">{error}</p>}

      {loading && !data ? (
        <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
          <SkeletonTable rows={8} columns={4} />
        </div>
      ) : data && pricedCount === 0 ? (
        <EmptyState
          icon={<IconTag width={20} height={20} />}
          title="No selling prices yet"
          description="Selling prices appear here once the Master Data Team publishes them. Try another date if you're looking for older prices."
        />
      ) : (
        <div className={`bg-white rounded-2xl shadow-card border border-sage-100 overflow-x-auto ${loading ? "opacity-60" : ""}`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
                <th className="text-left px-4 py-2.5">Item</th>
                <th className="text-left px-3 py-2.5 hidden sm:table-cell">Category</th>
                <th className="text-right px-4 py-2.5 whitespace-nowrap">Selling Price</th>
                <th className="text-right px-4 py-2.5 whitespace-nowrap hidden sm:table-cell">Published</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sage-100">
              {filtered.map((r) => (
                <tr key={r.product_id} className="hover:bg-sage-50/50 transition-colors duration-100">
                  <td className="px-4 py-2.5">
                    <p className="text-crate-950">
                      {r.description}
                      <ProductPromotion productId={r.product_id} className="ml-1.5" />
                    </p>
                    <p className="text-xs text-crate-800/40">
                      {r.product_code}
                      {r.pos_code ? ` · POS ${r.pos_code}` : ""}
                    </p>
                  </td>
                  <td className="px-3 py-2.5 hidden sm:table-cell">
                    <CategoryBadge name={r.category_name} />
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    {r.selling_price !== null ? (
                      <span className="font-semibold text-crate-950">
                        Rs. {r.selling_price.toFixed(2)}
                        <span className="text-xs font-normal text-crate-800/40"> / {r.unit_code}</span>
                      </span>
                    ) : (
                      <span className="text-crate-800/20">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-crate-800/50 whitespace-nowrap hidden sm:table-cell">
                    {r.published_at ? formatPublished(r.published_at) : ""}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-sm text-crate-800/35">
                    No items match your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-crate-800/35 px-1">
        Selling prices are set by SPAR Head Office (Master Data Team) and can't be changed here. Pick a date to see
        the prices that applied on that day.
      </p>
    </div>
  );
}
