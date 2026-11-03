import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { CostPrices, downloadTeamCostPricesZip, fetchTeamCostPrices } from "../../api/masterData";
import EmptyState from "../shared/EmptyState";
import { IconChevronDown, IconTag } from "../shared/Icons";
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

function shortDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/**
 * Master Data Team: the Cost Price column of the sheet Admin sent, split by
 * the supplier whose price it is. Download gives one POS-import Excel file
 * per supplier, zipped.
 */
export default function CostPricesView() {
  const [data, setData] = useState<CostPrices | null>(null);
  const [notSentYet, setNotSentYet] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [supplier, setSupplier] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    fetchTeamCostPrices()
      .then(setData)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) setNotSentYet(true);
        else setError(err instanceof ApiError ? err.message : "Could not load cost prices.");
      })
      .finally(() => setLoading(false));
  }, []);

  const groups = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    return data.suppliers
      .filter((s) => !supplier || s.supplier_name === supplier)
      .map((s) => ({
        ...s,
        items: q
          ? s.items.filter(
              (i) =>
                i.description.toLowerCase().includes(q) ||
                i.pos_code.toLowerCase().includes(q) ||
                i.product_code.toLowerCase().includes(q)
            )
          : s.items,
      }))
      .filter((s) => s.items.length > 0);
  }, [data, search, supplier]);

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      await downloadTeamCostPricesZip();
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
        description="Cost prices appear here once Admin clicks Send to Master Data."
      />
    );
  }

  if (!data) {
    return (
      <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">
        {error ?? "Could not load cost prices."}
      </div>
    );
  }

  const itemCount = data.suppliers.reduce((n, s) => n + s.items.length, 0);
  const searching = search.trim() !== "";

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4 flex flex-wrap items-center gap-3">
        <div className="mr-2">
          <p className="text-[10px] uppercase tracking-wide text-crate-800/40">Version from Admin</p>
          <p className="text-sm text-crate-950 font-semibold">
            v{data.version} · {formatDateTime(data.sent_at)}
          </p>
          <p className="text-xs text-crate-800/50">
            {data.suppliers.length} suppliers · {itemCount} items
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
          value={supplier}
          onChange={(e) => setSupplier(e.target.value)}
          className="border border-sage-300 bg-sage-50/60 rounded-full px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
        >
          <option value="">All suppliers</option>
          {data.suppliers.map((s) => (
            <option key={s.supplier_name} value={s.supplier_name}>
              {s.supplier_name}
            </option>
          ))}
        </select>
        <button
          onClick={handleDownload}
          disabled={downloading || data.suppliers.length === 0}
          title="One Excel file per supplier (POS import format: code + cost price), in one zip"
          className="ml-auto text-sm bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-4 py-2 font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
        >
          {downloading ? "Preparing…" : "Download ZIP (Excel per supplier)"}
        </button>
      </div>

      {error && <p className="text-tomato-600 text-sm px-1">{error}</p>}
      {data.skipped_no_pos_code.length > 0 && (
        <details className="rounded-2xl bg-mango-500/10 border border-mango-500/25 px-4 py-3 text-sm text-[#8A5A0D]">
          <summary className="cursor-pointer">
            {data.skipped_no_pos_code.length} item{data.skipped_no_pos_code.length === 1 ? " has" : "s have"} a cost
            price but no POS code, so {data.skipped_no_pos_code.length === 1 ? "it isn't" : "they aren't"} in the files
          </summary>
          <p className="mt-1 text-xs">{data.skipped_no_pos_code.join(", ")}</p>
        </details>
      )}

      {groups.length === 0 ? (
        <p className="text-sm text-crate-800/40 text-center py-6">No items match.</p>
      ) : (
        groups.map((s) => {
          const isOpen = searching || supplier !== "" || open[s.supplier_name];
          return (
            <div key={s.supplier_name} className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
              <button
                onClick={() => setOpen((o) => ({ ...o, [s.supplier_name]: !o[s.supplier_name] }))}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-sage-50/50 transition-colors duration-100"
              >
                <span className="font-semibold text-crate-950">{s.supplier_name} Cost Prices</span>
                <span className="flex items-center gap-2 text-xs text-crate-800/50">
                  {s.items.length} item{s.items.length === 1 ? "" : "s"}
                  <IconChevronDown
                    width={16}
                    height={16}
                    className={`transition-transform duration-150 ${isOpen ? "rotate-180" : ""}`}
                  />
                </span>
              </button>
              {isOpen && (
                <div className="overflow-x-auto border-t border-sage-100">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
                        <th className="text-left px-4 py-2">POS Code</th>
                        <th className="text-left px-3 py-2">Item</th>
                        <th className="text-left px-3 py-2 hidden sm:table-cell">Category</th>
                        <th className="text-right px-4 py-2 whitespace-nowrap">Cost Price</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-sage-100">
                      {s.items.map((i) => (
                        <tr key={i.product_id}>
                          <td className="px-4 py-2 text-crate-800/70 whitespace-nowrap">{i.pos_code}</td>
                          <td className="px-3 py-2 text-crate-950">
                            {i.description}
                            <span className="block text-xs text-crate-800/40">{i.product_code}</span>
                          </td>
                          <td className="px-3 py-2 hidden sm:table-cell">
                            <CategoryBadge name={i.category_name} />
                          </td>
                          <td className="px-4 py-2 text-right whitespace-nowrap">
                            <span className="font-semibold text-crate-950">Rs. {i.cost_price.toFixed(2)}</span>
                            {i.price_date && (
                              <span className="block text-[10px] text-crate-800/40">{shortDate(i.price_date)}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })
      )}
      <p className="text-[11px] text-crate-800/35 px-1">
        Each item's Cost Price is the highest supplier price on the Master Data Sheet Admin sent, listed under that
        supplier. The ZIP holds one Excel file per supplier in the POS import layout (product code + cost price).
      </p>
    </div>
  );
}
