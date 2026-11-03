import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { SellingPrices, downloadTeamSellingPricesExcel, fetchTeamSellingPrices } from "../../api/masterData";
import EmptyState from "../shared/EmptyState";
import { IconTag } from "../shared/Icons";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { SkeletonTable } from "../shared/ui/Skeleton";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Master Data Team: the Selling Price column of the sheet Admin sent.
 * Download gives one POS-import Excel file (code + selling price).
 */
export default function SellingPricesView() {
  const [data, setData] = useState<SellingPrices | null>(null);
  const [notSentYet, setNotSentYet] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    fetchTeamSellingPrices()
      .then(setData)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) setNotSentYet(true);
        else setError(err instanceof ApiError ? err.message : "Could not load selling prices.");
      })
      .finally(() => setLoading(false));
  }, []);

  const items = data?.items ?? [];
  const categories = useMemo(() => Array.from(new Set(items.map((i) => i.category_name))), [items]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((i) => {
      if (category && i.category_name !== category) return false;
      if (!q) return true;
      return (
        i.description.toLowerCase().includes(q) ||
        i.pos_code.toLowerCase().includes(q) ||
        i.product_code.toLowerCase().includes(q)
      );
    });
  }, [items, search, category]);

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      await downloadTeamSellingPricesExcel();
    } catch {
      setError("Could not download the file. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        <SkeletonTable rows={8} columns={4} />
      </div>
    );
  }

  if (notSentYet) {
    return (
      <EmptyState
        icon={<IconTag width={20} height={20} />}
        title="Nothing sent yet"
        description="Selling prices appear here once Admin clicks Send to Master Data."
      />
    );
  }

  if (!data) {
    return (
      <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">
        {error ?? "Could not load selling prices."}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4 flex flex-wrap items-center gap-3">
        <div className="mr-2">
          <p className="text-[10px] uppercase tracking-wide text-crate-800/40">Version from Admin</p>
          <p className="text-sm text-crate-950 font-semibold">
            v{data.version} · {formatDateTime(data.sent_at)}
          </p>
          <p className="text-xs text-crate-800/50">
            {items.length} items · {data.without_selling_price} without a selling price
          </p>
        </div>
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
        <button
          onClick={handleDownload}
          disabled={downloading || items.length === 0}
          title="One Excel file in the POS import format (product code + selling price)"
          className="ml-auto text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-4 py-2 font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
        >
          {downloading ? "Preparing…" : "Download Excel"}
        </button>
      </div>

      {error && <p className="text-tomato-600 text-sm px-1">{error}</p>}
      {data.skipped_no_pos_code.length > 0 && (
        <details className="rounded-2xl bg-mango-500/10 border border-mango-500/25 px-4 py-3 text-sm text-[#8A5A0D]">
          <summary className="cursor-pointer">
            {data.skipped_no_pos_code.length} item{data.skipped_no_pos_code.length === 1 ? " has" : "s have"} a selling
            price but no POS code, so {data.skipped_no_pos_code.length === 1 ? "it isn't" : "they aren't"} in the file
          </summary>
          <p className="mt-1 text-xs">{data.skipped_no_pos_code.join(", ")}</p>
        </details>
      )}

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
              <th className="text-left px-4 py-2.5">POS Code</th>
              <th className="text-left px-3 py-2.5">Item</th>
              <th className="text-left px-3 py-2.5 hidden sm:table-cell">Category</th>
              <th className="text-right px-4 py-2.5 whitespace-nowrap">Selling Price</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-sage-100">
            {filtered.map((i) => (
              <tr key={i.product_id} className="hover:bg-sage-50/50 transition-colors duration-100">
                <td className="px-4 py-2 text-crate-800/70 whitespace-nowrap">{i.pos_code}</td>
                <td className="px-3 py-2 text-crate-950">
                  {i.description}
                  <span className="block text-xs text-crate-800/40">{i.product_code}</span>
                </td>
                <td className="px-3 py-2 hidden sm:table-cell">
                  <CategoryBadge name={i.category_name} />
                </td>
                <td className="px-4 py-2 text-right whitespace-nowrap">
                  <span className="font-semibold text-crate-950">Rs. {i.selling_price.toFixed(2)}</span>
                  {i.published_selling_price !== i.selling_price && (
                    <span className="block text-[10px] text-[#8A5A0D]">Not published yet</span>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-sm text-crate-800/35">
                  No items match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-crate-800/35 px-1">
        Selling prices from the Master Data Sheet Admin sent. Download Excel gives one file in the POS import layout
        (product code + selling price).
      </p>
    </div>
  );
}
