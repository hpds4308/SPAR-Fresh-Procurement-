import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { Product, fetchProducts } from "../../api/orders";
import { LastPrice, PriceWindow, fetchLastPrices, fetchPriceWindow, fetchMyPrices, submitPrices } from "../../api/pricing";
import { CategoryBadge } from "../shared/ui/CategoryBadge";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

export default function PriceForm({ onSubmitted }: { onSubmitted: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [window_, setWindow] = useState<PriceWindow | null>(null);
  const [prices, setPrices] = useState<Record<number, string>>({});
  const [lastPrices, setLastPrices] = useState<Record<number, LastPrice>>({});
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [p, w] = await Promise.all([fetchProducts(), fetchPriceWindow()]);
        if (cancelled) return;
        setProducts(p);
        setWindow(w);

        const mine = await fetchMyPrices(w.delivery_date);
        if (cancelled) return;

        // Last price ever quoted per product, regardless of date. Also
        // doubles as the "new delivery date" fallback below: when this
        // date has no submission yet, it's necessarily the supplier's
        // most recent earlier one.
        let last: LastPrice[] = [];
        try {
          last = await fetchLastPrices();
          if (cancelled) return;
        } catch {
          // Non-critical — the form still works fine without this reference.
        }
        const lastMap: Record<number, LastPrice> = {};
        for (const lp of last) lastMap[lp.product_id] = lp;
        setLastPrices(lastMap);

        // Pre-fill priority: this delivery date's own submission first;
        // otherwise carry forward the supplier's latest previous price as
        // a starting default. Either way these are just starting values —
        // nothing is "submitted" for this date until Submit is clicked.
        const prefill: Record<number, string> = {};
        for (const mp of mine) prefill[mp.product_id] = String(mp.price);
        for (const lp of last) {
          if (!(lp.product_id in prefill)) prefill[lp.product_id] = String(lp.price);
        }
        setPrices(prefill);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the price form.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const categories = useMemo(() => {
    const set = new Set(products.map((p) => p.category_name));
    return ["ALL", ...Array.from(set).sort()];
  }, [products]);

  const filtered = useMemo(() => {
    return products.filter((p) => {
      if (category !== "ALL" && p.category_name !== category) return false;
      if (search.trim() && !p.description.toLowerCase().includes(search.trim().toLowerCase())) return false;
      return true;
    });
  }, [products, category, search]);

  const lineCount = useMemo(
    () => Object.values(prices).filter((v) => parseFloat(v) > 0).length,
    [prices]
  );

  function setPrice(productId: number, value: string) {
    setPrices((prev) => ({ ...prev, [productId]: value }));
  }

  function clearAll() {
    setPrices({});
  }

  function shortDate(iso: string): string {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  }

  async function handleSubmit() {
    setError(null);
    const entries = Object.entries(prices)
      .map(([productId, price]) => ({ product_id: Number(productId), price: parseFloat(price) }))
      .filter((e) => e.price > 0);

    if (entries.length === 0) {
      setError("Enter a price for at least one product.");
      return;
    }

    setSubmitting(true);
    try {
      await submitPrices(entries);
      setSuccess(true);
      onSubmitted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit prices. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-8 text-crate-800/40 text-sm text-center">
        Loading products…
      </div>
    );
  }

  if (window_ && !window_.is_open) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6">
        <p className="text-crate-800 font-semibold">Price submission is closed for today.</p>
        <p className="text-crate-800/60 text-sm mt-1">
          The daily cutoff is {window_.cutoff_time}. Please come back before {window_.cutoff_time}{" "}
          tomorrow to submit prices for the next delivery window.
        </p>
      </div>
    );
  }

  if (success) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6">
        <p className="text-crate-700 font-semibold">Prices submitted successfully.</p>
        <p className="text-crate-800/60 text-sm mt-1">
          They apply to delivery on {window_ ? formatDate(window_.delivery_date) : "today"}.
          You can still adjust them before the {window_?.cutoff_time} cutoff.
        </p>
        <button
          onClick={() => setSuccess(false)}
          className="mt-4 text-sm text-crate-700 border border-sage-300 rounded-full px-4 py-1.5 hover:bg-sage-50 transition-colors duration-150"
        >
          Back to price entry
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
      <div className="p-6 border-b border-sage-100">
        {window_ && (
          <p className="text-sm text-crate-800/70">
            Pricing for delivery on <span className="font-medium text-crate-800">{formatDate(window_.delivery_date)}</span>{" "}
            &middot; closes at {window_.cutoff_time} today &middot; you can resubmit to update a price
            before then
          </p>
        )}
        <div className="flex flex-col sm:flex-row gap-3 mt-4">
          <input
            placeholder="Search products…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 placeholder:text-crate-950/35 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
          />
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
          >
            {categories.map((c) => (
              <option key={c} value={c}>
                {c === "ALL" ? "All categories" : c}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="max-h-[28rem] overflow-y-auto divide-y divide-sage-100">
        {filtered.length === 0 && (
          <p className="p-6 text-sm text-crate-800/35 text-center">No products match your search.</p>
        )}
        {filtered.map((p) => {
          const last = lastPrices[p.id];
          return (
            <div key={p.id} className="flex items-center justify-between px-6 py-3 hover:bg-sage-50/50 transition-colors duration-100">
              <div className="min-w-0">
                <p className="text-sm text-crate-950 truncate">{p.description}</p>
                <div className="flex items-center flex-wrap gap-1.5 mt-0.5">
                  <span className="text-xs text-crate-800/40">
                    {p.product_code}
                    {p.subcategory ? ` · ${p.subcategory}` : ""}
                    {last && (
                      <span className="text-crate-800/30">
                        {" "}
                        &middot; last: Rs. {last.price.toFixed(2)} ({shortDate(last.delivery_date)})
                      </span>
                    )}
                  </span>
                  <CategoryBadge name={p.category_name} />
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-4">
                <span className="text-xs text-crate-800/40">Rs.</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0.00"
                  value={prices[p.id] ?? ""}
                  onChange={(e) => setPrice(p.id, e.target.value)}
                  className="w-24 border border-sage-300 bg-sage-50/60 rounded-full px-3 py-1.5 text-sm text-right text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
                />
                <span className="text-xs text-crate-800/40 w-10">/{p.unit_code}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="p-6 border-t border-sage-100 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <p className="text-sm text-crate-800/60">
            {lineCount} product{lineCount === 1 ? "" : "s"} with a price entered
          </p>
        </div>
        <div className="flex items-center gap-3">
          {error && <p className="text-tomato-600 text-sm">{error}</p>}
          <button
            onClick={clearAll}
            disabled={lineCount === 0}
            title="Clears the values shown on this form only — does not affect anything already submitted."
            className="border border-sage-300 text-crate-800/70 rounded-full px-4 py-2.5 text-sm font-medium hover:bg-sage-50 active:scale-[0.98] disabled:opacity-40 disabled:hover:bg-transparent transition-all duration-150"
          >
            Clear All
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || lineCount === 0}
            className="bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-5 py-2.5 text-sm font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
          >
            {submitting ? "Submitting…" : "Submit Prices"}
          </button>
        </div>
      </div>
    </div>
  );
}
