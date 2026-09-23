import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { compareProductDisplayOrder, fetchProducts, Product } from "../../api/orders";
import { fetchReferencePrices, KeellsSyncResult, ReferencePrice, syncKeellsPrices } from "../../api/pricing";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { IconTag } from "../shared/Icons";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function todayIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

// This page is sync-only, not hand-editable: prices come exclusively from
// "Sync from Keells Now" (or the daily scheduled scrape), which replaces
// the whole day's KEELLS prices in one shot — see
// keells_scrape_service.run_scrape / pricing_service.clear_reference_prices.
// A product with no synced price for the selected date is left out of the
// list entirely rather than shown as a blank row.
export default function AdminKeellsPrices() {
  const [products, setProducts] = useState<Product[]>([]);
  const [prices, setPrices] = useState<ReferencePrice[]>([]);
  const [deliveryDate, setDeliveryDate] = useState<string>(todayIso());
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<KeellsSyncResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  function reloadPrices() {
    return fetchReferencePrices(deliveryDate).then(setPrices);
  }

  async function handleSyncNow() {
    setSyncing(true);
    setSyncError(null);
    setSyncResult(null);
    try {
      const result = await syncKeellsPrices(deliveryDate);
      setSyncResult(result);
      if (result.delivery_date === deliveryDate) {
        await reloadPrices();
      }
    } catch (err) {
      setSyncError(err instanceof ApiError ? err.message : "Could not sync prices from Keells.");
    } finally {
      setSyncing(false);
    }
  }

  useEffect(() => {
    fetchProducts()
      .then(setProducts)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load products."));
  }, []);

  useEffect(() => {
    if (!deliveryDate) return;
    let cancelled = false;
    setLoading(true);
    fetchReferencePrices(deliveryDate)
      .then((data) => {
        if (cancelled) return;
        setPrices(data);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load Keells prices."))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deliveryDate]);

  const priceByProductId = useMemo(() => {
    const map = new Map<number, number>();
    for (const p of prices) map.set(p.product_id, p.price);
    return map;
  }, [prices]);

  const categories = useMemo(() => Array.from(new Set(products.map((p) => p.category_name))).sort(), [products]);

  // Only products with an actual synced price show up — no blank/empty rows.
  const filteredProducts = useMemo(() => {
    const q = search.trim().toLowerCase();
    return products
      .filter((p) => priceByProductId.has(p.id))
      .filter((p) => (category ? p.category_name === category : true))
      .filter((p) => (q ? p.description.toLowerCase().includes(q) || p.product_code.toLowerCase().includes(q) : true))
      .sort(compareProductDisplayOrder);
  }, [products, priceByProductId, search, category]);

  if (error && products.length === 0) {
    return (
      <div className="rounded-2xl bg-tomato-500/10 border border-tomato-500/25 p-6 text-tomato-600 text-sm">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-crate-800/70">Order Date</label>
          <input
            type="date"
            value={deliveryDate}
            onChange={(e) => setDeliveryDate(e.target.value)}
            className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
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
          <span className="text-xs text-crate-800/40">{filteredProducts.length} items</span>
          <button
            type="button"
            disabled={syncing || !deliveryDate}
            onClick={handleSyncNow}
            className="border border-crate-700/30 bg-crate-700 hover:bg-crate-800 rounded-full px-4 py-1.5 text-sm text-white transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {syncing ? "Syncing from Keells…" : "Sync from Keells Now"}
          </button>
        </div>
        {deliveryDate && (
          <p className="text-xs text-crate-800/40 mt-3">
            Keells prices are sync-only — there's nothing to type in here. "Sync from Keells Now" scrapes
            keellssuper.com directly (this also runs automatically once a day), replacing every price below for{" "}
            {formatDate(deliveryDate)} with what it finds. A product with no current match from Keells simply won't
            appear in the list.
          </p>
        )}
        {syncError && <p className="text-xs text-tomato-600 mt-2">{syncError}</p>}
        {syncResult && (
          <p className="text-xs text-crate-700 mt-2">
            Synced {syncResult.saved} price{syncResult.saved === 1 ? "" : "s"} for {formatDate(syncResult.delivery_date)}
            {syncResult.unmatched.length > 0 && (
              <>
                {" "}
                — {syncResult.unmatched.length} item{syncResult.unmatched.length === 1 ? "" : "s"} didn't match a
                known product: {syncResult.unmatched.map((u) => u.system_name || u.dc_code).join(", ")}
              </>
            )}
            .
          </p>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        {loading ? (
          <SkeletonTable rows={8} columns={2} />
        ) : filteredProducts.length === 0 ? (
          <EmptyState
            icon={<IconTag width={20} height={20} />}
            title={prices.length === 0 ? "No Keells prices synced for this date yet" : "No products match your filters"}
          />
        ) : (
          <div className="divide-y divide-sage-100">
            {filteredProducts.map((p) => (
              <div key={p.id} className="flex items-center justify-between px-5 py-3 hover:bg-sage-50/50 transition-colors duration-100">
                <div className="min-w-0">
                  <p className="text-sm text-crate-950 truncate">{p.description}</p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-xs text-crate-800/40">{p.product_code}</span>
                    <CategoryBadge name={p.category_name} />
                  </div>
                </div>
                <div className="shrink-0 ml-4 text-sm text-crate-950 tabular-nums">
                  Rs. {priceByProductId.get(p.id)?.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {error && products.length > 0 && <p className="text-tomato-600 text-sm px-1">{error}</p>}
    </div>
  );
}
