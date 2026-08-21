import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import {
  Product,
  OrderWindow,
  fetchProducts,
  fetchOrderWindow,
  submitOrder,
} from "../../api/orders";
import { CategoryBadge } from "../shared/ui/CategoryBadge";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

export default function OrderForm({ onSubmitted }: { onSubmitted: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [window_, setWindow] = useState<OrderWindow | null>(null);
  const [quantities, setQuantities] = useState<Record<number, string>>({});
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
        const [p, w] = await Promise.all([fetchProducts(), fetchOrderWindow()]);
        if (!cancelled) {
          setProducts(p);
          setWindow(w);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load order form.");
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
    () => Object.values(quantities).filter((v) => parseFloat(v) > 0).length,
    [quantities]
  );

  function setQty(productId: number, value: string) {
    setQuantities((prev) => ({ ...prev, [productId]: value }));
  }

  async function handleSubmit() {
    setError(null);
    const lines = Object.entries(quantities)
      .map(([productId, qty]) => ({ product_id: Number(productId), quantity: parseFloat(qty) }))
      .filter((l) => l.quantity > 0);

    if (lines.length === 0) {
      setError("Enter a quantity for at least one product.");
      return;
    }

    setSubmitting(true);
    try {
      await submitOrder(lines);
      setSuccess(true);
      setQuantities({});
      onSubmitted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit the order. Please try again.");
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
        <p className="text-crate-800 font-semibold">Ordering is closed for today.</p>
        <p className="text-crate-800/60 text-sm mt-1">
          The daily cutoff is {window_.cutoff_time}. Please come back before {window_.cutoff_time}{" "}
          tomorrow to place tomorrow's order.
        </p>
      </div>
    );
  }

  if (success) {
    return (
      <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 p-6">
        <p className="text-crate-700 font-semibold">Order submitted successfully.</p>
        <p className="text-crate-800/60 text-sm mt-1">
          It will be delivered on {window_ ? formatDate(window_.delivery_date) : "today"}.
          You can review it under "My Orders".
        </p>
        <button
          onClick={() => setSuccess(false)}
          className="mt-4 text-sm text-crate-700 border border-sage-300 rounded-full px-4 py-1.5 hover:bg-sage-50 transition-colors duration-150"
        >
          Place another order
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden">
      <div className="p-6 border-b border-sage-100">
        {window_ && (
          <p className="text-sm text-crate-800/70">
            Ordering for <span className="font-medium text-crate-800">today, {formatDate(window_.delivery_date)}</span>{" "}
            &middot; closes at {window_.cutoff_time} today
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
        {filtered.map((p) => (
          <div key={p.id} className="flex items-center justify-between px-6 py-3 hover:bg-sage-50/50 transition-colors duration-100">
            <div className="min-w-0">
              <p className="text-sm text-crate-950 truncate">{p.description}</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-xs text-crate-800/40">
                  {p.product_code}
                  {p.subcategory ? ` · ${p.subcategory}` : ""}
                </span>
                <CategoryBadge name={p.category_name} />
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0 ml-4">
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="0"
                value={quantities[p.id] ?? ""}
                onChange={(e) => setQty(p.id, e.target.value)}
                className="w-24 border border-sage-300 bg-sage-50/60 rounded-full px-3 py-1.5 text-sm text-right text-crate-950 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
              />
              <span className="text-xs text-crate-800/40 w-10">{p.unit_code}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="p-6 border-t border-sage-100 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-crate-800/60">
          {lineCount} product{lineCount === 1 ? "" : "s"} with a quantity entered
        </p>
        <div className="flex items-center gap-3">
          {error && <p className="text-tomato-600 text-sm">{error}</p>}
          <button
            onClick={handleSubmit}
            disabled={submitting || lineCount === 0}
            className="bg-gradient-to-b from-crate-700 to-crate-800 text-white rounded-full px-5 py-2.5 text-sm font-semibold hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100 shadow-md shadow-crate-800/20 transition-all duration-150"
          >
            {submitting ? "Submitting…" : "Submit Order"}
          </button>
        </div>
      </div>
    </div>
  );
}
