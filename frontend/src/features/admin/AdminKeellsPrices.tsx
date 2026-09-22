import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { compareProductDisplayOrder, fetchProducts, Product } from "../../api/orders";
import {
  fetchLastReferencePrices,
  fetchPriceWindow,
  fetchReferencePrices,
  importKeellsPrices,
  KeellsImportResult,
  setReferencePrice,
} from "../../api/pricing";
import EmptyState from "../shared/EmptyState";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { CategoryBadge } from "../shared/ui/CategoryBadge";
import { IconTag } from "../shared/Icons";

type CellState = "idle" | "saving" | "saved" | "error";

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

export default function AdminKeellsPrices() {
  const [products, setProducts] = useState<Product[]>([]);
  const [deliveryDate, setDeliveryDate] = useState<string>("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [cellState, setCellState] = useState<Record<number, CellState>>({});
  const [lastPrices, setLastPrices] = useState<Record<number, { price: number; delivery_date: string }>>({});
  const [carriedForwardIds, setCarriedForwardIds] = useState<Set<number>>(new Set());

  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<KeellsImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function reloadLastPrices() {
    return fetchLastReferencePrices().then((data) => {
      const next: Record<number, { price: number; delivery_date: string }> = {};
      for (const r of data) next[r.product_id] = { price: r.price, delivery_date: r.delivery_date };
      setLastPrices(next);
    });
  }

  async function handleImportFile(file: File) {
    setImporting(true);
    setImportError(null);
    setImportResult(null);
    try {
      const result = await importKeellsPrices(file, deliveryDate);
      setImportResult(result);
      // Reloading lastPrices (rather than deliveryDate) re-triggers the
      // effect below regardless of whether the imported rows landed on
      // today's deliveryDate, since that effect depends on both.
      await reloadLastPrices();
    } catch (err) {
      setImportError(err instanceof ApiError ? err.message : "Could not import that file.");
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  useEffect(() => {
    fetchProducts()
      .then(setProducts)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load products."));
    fetchPriceWindow()
      .then((w) => setDeliveryDate(w.delivery_date))
      .catch(() => {});
    reloadLastPrices().catch(() => {});
  }, []);

  useEffect(() => {
    if (!deliveryDate) return;
    let cancelled = false;
    setLoading(true);
    fetchReferencePrices(deliveryDate)
      .then((data) => {
        if (cancelled) return;
        const next: Record<number, string> = {};
        const confirmedIds = new Set<number>();
        for (const r of data) {
          next[r.product_id] = String(r.price);
          confirmedIds.add(r.product_id);
        }
        const nextCarried = new Set<number>();
        for (const [productIdStr, last] of Object.entries(lastPrices)) {
          const productId = Number(productIdStr);
          if (!confirmedIds.has(productId)) {
            next[productId] = String(last.price);
            nextCarried.add(productId);
          }
        }
        setDrafts(next);
        setCarriedForwardIds(nextCarried);
        setCellState({});
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load Keells prices."))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deliveryDate, lastPrices]);

  const categories = useMemo(() => Array.from(new Set(products.map((p) => p.category_name))).sort(), [products]);

  const filteredProducts = useMemo(() => {
    const q = search.trim().toLowerCase();
    return products
      .filter((p) => (category ? p.category_name === category : true))
      .filter((p) => (q ? p.description.toLowerCase().includes(q) || p.product_code.toLowerCase().includes(q) : true))
      .sort(compareProductDisplayOrder);
  }, [products, search, category]);

  async function saveField(productId: number, raw: string) {
    const trimmed = raw.trim();
    const value = trimmed === "" ? null : Number(trimmed);
    if (value !== null && (Number.isNaN(value) || value <= 0)) {
      setCellState((s) => ({ ...s, [productId]: "error" }));
      return;
    }
    setCellState((s) => ({ ...s, [productId]: "saving" }));
    try {
      await setReferencePrice(productId, deliveryDate, value);
      setCellState((s) => ({ ...s, [productId]: "saved" }));
      setCarriedForwardIds((prev) => {
        if (!prev.has(productId)) return prev;
        const next = new Set(prev);
        next.delete(productId);
        return next;
      });
      if (value !== null) {
        setLastPrices((prev) => ({ ...prev, [productId]: { price: value, delivery_date: deliveryDate } }));
      }
      setTimeout(() => setCellState((s) => (s[productId] === "saved" ? { ...s, [productId]: "idle" } : s)), 1500);
    } catch {
      setCellState((s) => ({ ...s, [productId]: "error" }));
    }
  }

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
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleImportFile(file);
            }}
          />
          <button
            type="button"
            disabled={importing || !deliveryDate}
            onClick={() => fileInputRef.current?.click()}
            className="border border-sage-300 bg-sage-50/60 hover:bg-sage-100 rounded-full px-4 py-1.5 text-sm text-crate-800/80 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {importing ? "Importing…" : "Import from Excel"}
          </button>
        </div>
        {deliveryDate && (
          <p className="text-xs text-crate-800/40 mt-3">
            Prices entered here for {formatDate(deliveryDate)} show up automatically on the Supplier Prices page's
            Keells Price column — no separate step needed. You can also import the scraper's .xlsx output above to
            fill in prices for {formatDate(deliveryDate)} in bulk.
          </p>
        )}
        {importError && <p className="text-xs text-tomato-600 mt-2">{importError}</p>}
        {importResult && (
          <p className="text-xs text-crate-700 mt-2">
            Imported {importResult.saved} price{importResult.saved === 1 ? "" : "s"} for{" "}
            {formatDate(importResult.delivery_date)}
            {importResult.unmatched.length > 0 && (
              <>
                {" "}
                — {importResult.unmatched.length} item{importResult.unmatched.length === 1 ? "" : "s"} from the file
                didn't match a known product: {importResult.unmatched.map((u) => u.system_name || u.dc_code).join(", ")}
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
          <EmptyState icon={<IconTag width={20} height={20} />} title="No products match your filters" />
        ) : (
          <div className="divide-y divide-sage-100">
            {filteredProducts.map((p) => {
              const state = cellState[p.id] ?? "idle";
              const isCarried = carriedForwardIds.has(p.id);
              return (
                <div key={p.id} className="flex items-center justify-between px-5 py-3 hover:bg-sage-50/50 transition-colors duration-100">
                  <div className="min-w-0">
                    <p className="text-sm text-crate-950 truncate">{p.description}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="text-xs text-crate-800/40">{p.product_code}</span>
                      <CategoryBadge name={p.category_name} />
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-0.5 shrink-0 ml-4">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-crate-800/40">Rs.</span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="—"
                        value={drafts[p.id] ?? ""}
                        onChange={(e) => {
                          setDrafts((d) => ({ ...d, [p.id]: e.target.value }));
                          setCarriedForwardIds((prev) => {
                            if (!prev.has(p.id)) return prev;
                            const next = new Set(prev);
                            next.delete(p.id);
                            return next;
                          });
                        }}
                        onBlur={(e) => saveField(p.id, e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                        className={`w-24 border rounded-full px-3 py-1.5 text-sm text-right focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-colors duration-150 ${
                          state === "error"
                            ? "border-tomato-500 ring-1 ring-tomato-500/30 bg-sage-50/60"
                            : isCarried
                            ? "border-mango-500/40 bg-mango-500/5 text-crate-800/70"
                            : "border-sage-300 bg-sage-50/60"
                        }`}
                      />
                      {state === "saving" && <span className="text-[10px] text-crate-800/35">…</span>}
                      {state === "saved" && <span className="text-[10px] text-crate-700">✓</span>}
                      {state === "error" && <span className="text-[10px] text-tomato-600">!</span>}
                    </div>
                    {isCarried && lastPrices[p.id] && (
                      <span className="text-[9px] text-mango-600/70 leading-none">
                        from {new Date(lastPrices[p.id].delivery_date + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {error && products.length > 0 && <p className="text-tomato-600 text-sm px-1">{error}</p>}
    </div>
  );
}
